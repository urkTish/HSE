// HSE.exe — launcher for the portable Windows edition of the HSE platform (portable/README.md).
//
// It runs everything from the folder it sits in: a PostgreSQL 16 cluster in data\pgdata, the API
// (uvicorn) and the timed jobs (app.scheduler) on the bundled Python, and the Next.js server on the
// bundled node.exe. Everything listens on 127.0.0.1 only. Closing the console window (or Ctrl+C,
// or `HSE.exe --stop`) stops the child processes and shuts PostgreSQL down cleanly.
package main

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// Set at build time: -ldflags "-X main.version=<git sha>".
var version = "dev"

const (
	dbName       = "hse"
	dbUser       = "hse"
	seedPassword = "Demo-Passw0rd!2026"
	loginPath    = "/en/login"
	healthPath   = "/api/v1/health"
)

type launcher struct {
	root, data                              string
	pgBin, python, node, backendDir, webDir string
	webServer                               string
	pgPort, apiPort, webPort, wantWebPort   int
	noBrowser                               bool

	logFile *os.File
	secrets map[string]string

	mu       sync.Mutex
	services []*service
	fatal    chan error
}

func main() {
	var (
		noBrowser = flag.Bool("no-browser", false, "do not open the browser (and do not wait for Enter on errors)")
		stop      = flag.Bool("stop", false, "ask a running launcher (same folder) to stop, and wait until it has")
		dataDir   = flag.String("data", "", `data folder (default: "data" next to HSE.exe)`)
		pgPort    = flag.Int("pg-port", 54329, "PostgreSQL port (127.0.0.1)")
		apiPort   = flag.Int("api-port", 54330, "API port (127.0.0.1); fixed, the web build points at it")
		webPort   = flag.Int("web-port", 3000, "preferred web port (127.0.0.1); the next free one is used if busy")
		showVer   = flag.Bool("version", false, "print the bundle version")
	)
	flag.Parse()
	if *showVer {
		fmt.Println(version)
		return
	}
	l, err := newLauncher(*dataDir)
	if err != nil {
		fail(err, *noBrowser)
	}
	l.pgPort, l.apiPort, l.wantWebPort, l.noBrowser = *pgPort, *apiPort, *webPort, *noBrowser
	if *stop {
		os.Exit(l.requestStop())
	}
	if err := l.run(); err != nil {
		fail(err, *noBrowser)
	}
}

func fail(err error, noPause bool) {
	fmt.Println()
	fmt.Println("  *** The HSE platform could not start or stopped with an error ***")
	fmt.Println()
	for _, line := range strings.Split(err.Error(), "\n") {
		fmt.Println("  " + line)
	}
	fmt.Println()
	if !noPause {
		fmt.Println("  Press Enter to close this window.")
		_, _ = bufio.NewReader(os.Stdin).ReadString('\n')
	}
	os.Exit(1)
}

func exeName(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func newLauncher(dataDir string) (*launcher, error) {
	exe, err := os.Executable()
	if err != nil {
		return nil, err
	}
	if r, err := filepath.EvalSymlinks(exe); err == nil {
		exe = r
	}
	root := filepath.Dir(exe)
	if dataDir == "" {
		dataDir = filepath.Join(root, "data")
	}
	dataDir, _ = filepath.Abs(dataDir)
	pyDefault := filepath.Join(root, "runtime", "python", "python.exe")
	if runtime.GOOS != "windows" {
		pyDefault = filepath.Join(root, "runtime", "python", "bin", "python3")
	}
	// HSE_* overrides exist only to try the launcher against a development checkout.
	l := &launcher{
		root:       root,
		data:       dataDir,
		pgBin:      envOr("HSE_PG_BIN", filepath.Join(root, "runtime", "pgsql", "bin")),
		python:     envOr("HSE_PYTHON", pyDefault),
		node:       envOr("HSE_NODE", filepath.Join(root, "runtime", "node", exeName("node"))),
		backendDir: envOr("HSE_BACKEND_DIR", filepath.Join(root, "app", "backend")),
		webDir:     envOr("HSE_WEB_DIR", filepath.Join(root, "app", "web")),
		fatal:      make(chan error, 8),
	}
	l.webServer = filepath.Join(l.webDir, "server.js")
	return l, nil
}

func (l *launcher) path(parts ...string) string {
	return filepath.Join(append([]string{l.data}, parts...)...)
}

// ---------------------------------------------------------------- output and logs

func (l *launcher) logf(format string, a ...any) {
	if l.logFile != nil {
		fmt.Fprintf(l.logFile, "%s  %s\n", time.Now().Format("2006-01-02 15:04:05"), fmt.Sprintf(format, a...))
	}
}

// say prints a line in the console window and writes it to launcher.log.
func (l *launcher) say(format string, a ...any) {
	msg := fmt.Sprintf(format, a...)
	fmt.Println("  " + msg)
	l.logf("%s", msg)
}

func rotateLogs(dir string) {
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".log") {
			continue
		}
		if info, err := e.Info(); err == nil && info.Size() > 10<<20 {
			p := filepath.Join(dir, e.Name())
			_ = os.Rename(p, p+".old")
		}
	}
}

// tail returns the last n lines of a log file, for error messages.
func tail(path string, n int) string {
	b, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	lines := strings.Split(strings.TrimRight(string(b), "\r\n"), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	for i, s := range lines {
		lines[i] = "    | " + strings.TrimRight(s, "\r")
	}
	return strings.Join(lines, "\n")
}

func (l *launcher) stepError(what, logPath string, err error) error {
	msg := fmt.Sprintf("%s failed: %v\nDetails are in %s", what, err, logPath)
	if t := tail(logPath, 15); t != "" {
		msg += "\nLast lines of that log:\n" + t
	}
	return errors.New(msg)
}

// ---------------------------------------------------------------- environment

type envMap struct {
	keys []string
	vals map[string]string
}

func envKey(k string) string {
	if runtime.GOOS == "windows" {
		return strings.ToUpper(k) // Windows environment names are case-insensitive
	}
	return k
}

func newEnv() *envMap {
	e := &envMap{vals: map[string]string{}}
	for _, kv := range os.Environ() {
		if i := strings.Index(kv, "="); i > 0 {
			e.set(kv[:i], kv[i+1:])
		}
	}
	return e
}

func (e *envMap) set(k, v string) {
	if _, ok := e.vals[envKey(k)]; !ok {
		e.keys = append(e.keys, k)
	}
	e.vals[envKey(k)] = v
}

func (e *envMap) del(k string) {
	delete(e.vals, envKey(k))
}

func (e *envMap) list() []string {
	out := make([]string, 0, len(e.vals))
	seen := map[string]bool{}
	for _, k := range e.keys {
		ek := envKey(k)
		if v, ok := e.vals[ek]; ok && !seen[ek] {
			seen[ek] = true
			out = append(out, k+"="+v)
		}
	}
	return out
}

// baseEnv is the parent environment cleaned of anything that could point the bundled runtimes at
// another Python, Node or PostgreSQL installed on the laptop.
func (l *launcher) baseEnv() *envMap {
	e := newEnv()
	for _, k := range []string{
		"PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "VIRTUAL_ENV", "CONDA_PREFIX", "NODE_OPTIONS",
		"NODE_PATH", "PGHOST", "PGHOSTADDR", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE",
		"PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "PGDATA", "PGOPTIONS", "PGSSLMODE",
	} {
		e.del(k)
	}
	noProxy := "127.0.0.1,localhost"
	if v := os.Getenv("NO_PROXY"); v != "" {
		noProxy += "," + v
	}
	e.set("NO_PROXY", noProxy)
	e.set("no_proxy", noProxy)
	e.set("PATH", l.pgBin+string(os.PathListSeparator)+os.Getenv("PATH"))
	return e
}

func (l *launcher) pgEnv() *envMap {
	e := l.baseEnv()
	e.set("PGHOST", "127.0.0.1")
	e.set("PGPORT", strconv.Itoa(l.pgPort))
	e.set("PGUSER", dbUser)
	e.set("PGPASSWORD", l.secrets["POSTGRES_PASSWORD"])
	e.set("PGCONNECT_TIMEOUT", "10")
	return e
}

// backendEnv: every portable-only switch is an environment variable set here; the application
// code is the same as the server deployment (ENVIRONMENT choice: portable/README.md).
func (l *launcher) backendEnv() *envMap {
	e := l.baseEnv()
	e.set("PYTHONNOUSERSITE", "1")
	e.set("PYTHONUTF8", "1")
	e.set("PYTHONUNBUFFERED", "1")
	e.set("PYTHONDONTWRITEBYTECODE", "1")
	e.set("DATABASE_URL", fmt.Sprintf("postgresql+psycopg://%s:%s@127.0.0.1:%d/%s",
		dbUser, l.secrets["POSTGRES_PASSWORD"], l.pgPort, dbName))
	e.set("ENVIRONMENT", "development")
	e.set("COOKIE_SECURE", "false")
	e.set("TRUST_PROXY_HEADERS", "false")
	e.set("FRONTEND_BASE_URL", fmt.Sprintf("http://127.0.0.1:%d", l.webPort))
	e.set("STORAGE_DIR", l.path("uploads"))
	e.set("CLAMAV_HOST", "")
	e.set("MFA_REQUIRED_ROLES", "")
	e.set("SEED_PASSWORD", seedPassword)
	for _, k := range []string{"JWT_SECRET", "FIELD_ENCRYPTION_KEY", "BLIND_INDEX_KEY", "ATTACHMENT_URL_SECRET"} {
		e.set(k, l.secrets[k])
	}
	for _, k := range []string{"HSE_CLOCK_AT", "HSE_CLOCK_MODE", "TEST_DATABASE_URL"} {
		e.del(k)
	}
	// Optional owner overrides (e.g. SMTP_*), data\config\settings.env.
	if extra, err := readEnvFile(l.path("config", "settings.env")); err == nil {
		for k, v := range extra {
			if envKey(k) == envKey("DATABASE_URL") || envKey(k) == envKey("STORAGE_DIR") {
				continue
			}
			e.set(k, v)
		}
	}
	return e
}

func (l *launcher) webEnv() *envMap {
	e := l.baseEnv()
	e.set("NODE_ENV", "production")
	e.set("NEXT_TELEMETRY_DISABLED", "1")
	e.set("HOSTNAME", "127.0.0.1")
	e.set("PORT", strconv.Itoa(l.webPort))
	return e
}

func readEnvFile(path string) (map[string]string, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	out := map[string]string{}
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(strings.TrimPrefix(line, "\ufeff"))
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if i := strings.Index(line, "="); i > 0 {
			out[strings.TrimSpace(line[:i])] = strings.TrimSpace(line[i+1:])
		}
	}
	return out, nil
}

// ---------------------------------------------------------------- secrets

const alnum = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

func randomSecret(n int) (string, error) {
	b := make([]byte, n)
	for i := range b {
		x, err := rand.Int(rand.Reader, big.NewInt(int64(len(alnum))))
		if err != nil {
			return "", err
		}
		b[i] = alnum[x.Int64()]
	}
	return string(b), nil
}

func (l *launcher) loadSecrets() error {
	path := l.path("config", "secrets.env")
	s, err := readEnvFile(path)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	if s == nil {
		s = map[string]string{}
	}
	keys := []string{"POSTGRES_PASSWORD", "JWT_SECRET", "FIELD_ENCRYPTION_KEY", "BLIND_INDEX_KEY", "ATTACHMENT_URL_SECRET"}
	changed := false
	for _, k := range keys {
		if len(s[k]) >= 32 {
			continue
		}
		if k == "POSTGRES_PASSWORD" && fileExists(l.path("pgdata", "PG_VERSION")) {
			return fmt.Errorf("%s is missing from %s, so the existing database cannot be opened.\n"+
				"Restore that file from your backup, or delete the data folder to start fresh.", k, path)
		}
		v, err := randomSecret(48)
		if err != nil {
			return err
		}
		s[k], changed = v, true
	}
	if changed {
		var b strings.Builder
		b.WriteString("# Generated by HSE.exe on first start. Keep this file with the data folder:\n")
		b.WriteString("# without it the database and the encrypted fields cannot be read.\n")
		for _, k := range keys {
			fmt.Fprintf(&b, "%s=%s\n", k, s[k])
		}
		if err := writeFileAtomic(path, []byte(b.String())); err != nil {
			return err
		}
	}
	l.secrets = s
	return nil
}

func writeFileAtomic(path string, b []byte) error {
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func fileExists(p string) bool {
	_, err := os.Stat(p)
	return err == nil
}

const settingsTemplate = `# Optional settings for the portable HSE platform, read by HSE.exe at every start.
# One KEY=value per line; lines starting with # are ignored. Restart HSE.exe after a change.
# Examples (remove the # to use):
#
# Send emails through your mail server (otherwise they stay in the outbox):
# SMTP_HOST=smtp.office365.com
# SMTP_PORT=587
# SMTP_USER=you@company.com
# SMTP_PASSWORD=...
# SMTP_FROM=HSE Platform <you@company.com>
#
# Make two-step verification compulsory for HSE Managers again:
# MFA_REQUIRED_ROLES=hse_manager,admin
`

// ---------------------------------------------------------------- ports

func portFree(p int) bool {
	addr := net.JoinHostPort("127.0.0.1", strconv.Itoa(p))
	if c, err := net.DialTimeout("tcp", addr, 300*time.Millisecond); err == nil {
		_ = c.Close()
		return false
	}
	ln, err := net.Listen("tcp", addr)
	if err != nil {
		return false
	}
	_ = ln.Close()
	return true
}

func (l *launcher) pickWebPort() (int, error) {
	for p := l.wantWebPort; p < l.wantWebPort+10; p++ {
		if p != l.apiPort && p != l.pgPort && portFree(p) {
			return p, nil
		}
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer ln.Close()
	return ln.Addr().(*net.TCPAddr).Port, nil
}

func busyPortError(p int, what string) error {
	return fmt.Errorf("Port %d (needed for the %s) is already in use on this computer.\n"+
		"Another copy of the HSE platform may be running from a different folder: close its window.\n"+
		"Otherwise close the program using port %d, or restart Windows, then start HSE.exe again.", p, what, p)
}

// ---------------------------------------------------------------- processes

func (l *launcher) command(ctx context.Context, env *envMap, dir, exe string, args ...string) *exec.Cmd {
	var cmd *exec.Cmd
	if ctx != nil {
		cmd = exec.CommandContext(ctx, exe, args...)
	} else {
		cmd = exec.Command(exe, args...)
	}
	cmd.Dir = dir
	cmd.Env = env.list()
	hideWindow(cmd)
	return cmd
}

// runStep runs one preparation step to completion, its output appended to logs\<name>.log.
func (l *launcher) runStep(ctx context.Context, what, logName string, timeout time.Duration,
	env *envMap, dir, exe string, args ...string) error {
	logPath := l.path("logs", logName)
	f, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	fmt.Fprintf(f, "\n==== %s  %s %s\n", time.Now().Format(time.RFC3339), filepath.Base(exe), strings.Join(args, " "))
	sctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := l.command(sctx, env, dir, exe, args...)
	cmd.Stdout, cmd.Stderr = f, f
	l.logf("run %s: %s %v", what, exe, args)
	if err := cmd.Run(); err != nil {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if sctx.Err() != nil {
			err = fmt.Errorf("no answer after %s", timeout)
		}
		return l.stepError(what, logPath, err)
	}
	return nil
}

// output runs a short command and returns its standard output.
func (l *launcher) output(env *envMap, exe string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	cmd := l.command(ctx, env, l.data, exe, args...)
	out, err := cmd.CombinedOutput()
	l.logf("%s %v -> %v: %s", filepath.Base(exe), args, err, strings.TrimSpace(string(out)))
	return string(out), err
}

type service struct {
	name, logName string
	make          func() *exec.Cmd

	mu       sync.Mutex
	cmd      *exec.Cmd
	done     chan struct{}
	stopping bool
}

func (l *launcher) startService(s *service) error {
	f, err := os.OpenFile(l.path("logs", s.logName), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return err
	}
	fmt.Fprintf(f, "\n==== %s  start %s\n", time.Now().Format(time.RFC3339), s.name)
	cmd := s.make()
	cmd.Stdout, cmd.Stderr = f, f
	if err := cmd.Start(); err != nil {
		f.Close()
		return fmt.Errorf("could not start the %s: %w", s.name, err)
	}
	done := make(chan struct{})
	s.mu.Lock()
	s.cmd, s.done = cmd, done
	s.mu.Unlock()
	l.logf("started %s (pid %d)", s.name, cmd.Process.Pid)
	go func() {
		err := cmd.Wait()
		f.Close()
		l.logf("%s (pid %d) exited: %v", s.name, cmd.Process.Pid, err)
		close(done)
	}()
	return nil
}

func (s *service) exited() bool {
	s.mu.Lock()
	d := s.done
	s.mu.Unlock()
	if d == nil {
		return false
	}
	select {
	case <-d:
		return true
	default:
		return false
	}
}

func (s *service) stop() {
	s.mu.Lock()
	s.stopping = true
	cmd, done := s.cmd, s.done
	s.mu.Unlock()
	if cmd == nil || cmd.Process == nil {
		return
	}
	_ = cmd.Process.Kill()
	select {
	case <-done:
	case <-time.After(5 * time.Second):
	}
}

// supervise restarts a service that stops on its own once the platform is running (a few times).
func (l *launcher) supervise(ctx context.Context, s *service) {
	restarts := 0
	for {
		s.mu.Lock()
		done := s.done
		s.mu.Unlock()
		select {
		case <-ctx.Done():
			return
		case <-done:
		}
		s.mu.Lock()
		stopping := s.stopping
		s.mu.Unlock()
		if stopping || ctx.Err() != nil {
			return
		}
		restarts++
		if restarts > 5 {
			l.fatal <- l.stepError("The "+s.name, l.path("logs", s.logName), errors.New("it stopped repeatedly"))
			return
		}
		l.say("The %s stopped unexpectedly; restarting it (%d/5). See logs\\%s.", s.name, restarts, s.logName)
		select {
		case <-ctx.Done():
			return
		case <-time.After(3 * time.Second):
		}
		if err := l.startService(s); err != nil {
			l.fatal <- err
			return
		}
	}
}

// ---------------------------------------------------------------- PostgreSQL

func (l *launcher) pg(name string) string { return filepath.Join(l.pgBin, exeName(name)) }

func (l *launcher) pgRunning() bool {
	if !fileExists(l.path("pgdata", "postmaster.pid")) {
		return false
	}
	_, err := l.output(l.pgEnv(), l.pg("pg_ctl"), "status", "-D", l.path("pgdata"))
	return err == nil
}

func (l *launcher) stopPostgres() {
	if !l.pgRunning() {
		return
	}
	l.logf("stopping PostgreSQL")
	if _, err := l.output(l.pgEnv(), l.pg("pg_ctl"), "stop", "-D", l.path("pgdata"), "-m", "fast", "-w", "-t", "60"); err != nil {
		l.logf("pg_ctl stop -m fast failed: %v; trying immediate", err)
		_, _ = l.output(l.pgEnv(), l.pg("pg_ctl"), "stop", "-D", l.path("pgdata"), "-m", "immediate", "-w", "-t", "30")
	}
}

func (l *launcher) initCluster(ctx context.Context) error {
	pgdata := l.path("pgdata")
	_ = os.RemoveAll(pgdata) // a half-made cluster from an interrupted first start
	pwfile := l.path("run", "pw.tmp")
	if err := os.WriteFile(pwfile, []byte(l.secrets["POSTGRES_PASSWORD"]+"\n"), 0o600); err != nil {
		return err
	}
	defer os.Remove(pwfile)
	base := []string{"-D", pgdata, "-U", dbUser, "--pwfile=" + pwfile, "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C"}
	// ICU en-US collation sorts text like the server deployment (en_US.UTF-8); plain C is the fallback.
	err := l.runStep(ctx, "Creating the database", "initdb.log", 10*time.Minute, l.baseEnv(), l.data,
		l.pg("initdb"), append(base, "--locale-provider=icu", "--icu-locale=en-US")...)
	if err != nil && ctx.Err() == nil {
		l.logf("initdb with ICU failed (%v); retrying with the C locale", err)
		_ = os.RemoveAll(pgdata)
		err = l.runStep(ctx, "Creating the database", "initdb.log", 10*time.Minute, l.baseEnv(), l.data, l.pg("initdb"), base...)
	}
	if err != nil {
		_ = os.RemoveAll(pgdata)
		return err
	}
	conf := fmt.Sprintf(`
# ---- HSE portable edition (HSE.exe) ----
listen_addresses = '127.0.0.1'
port = %d
unix_socket_directories = ''
max_connections = 60
timezone = 'UTC'
log_timezone = 'UTC'
`, l.pgPort)
	f, err := os.OpenFile(filepath.Join(pgdata, "postgresql.conf"), os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = f.WriteString(conf)
	return err
}

func (l *launcher) startPostgres(ctx context.Context) error {
	opts := fmt.Sprintf("-p %d -c listen_addresses=127.0.0.1", l.pgPort)
	return l.runStep(ctx, "Starting PostgreSQL", "pg_ctl.log", 3*time.Minute, l.baseEnv(), l.data,
		l.pg("pg_ctl"), "start", "-D", l.path("pgdata"), "-l", l.path("logs", "postgres.log"), "-w", "-t", "150", "-o", opts)
}

func (l *launcher) ensureDatabase(ctx context.Context) error {
	out, err := l.output(l.pgEnv(), l.pg("psql"), "-d", "postgres", "-tAc",
		fmt.Sprintf("SELECT 1 FROM pg_database WHERE datname = '%s'", dbName))
	if err != nil {
		return fmt.Errorf("cannot connect to the bundled PostgreSQL: %v\n%s\nDetails: %s", err,
			strings.TrimSpace(out), l.path("logs", "postgres.log"))
	}
	if strings.TrimSpace(out) == "1" {
		return nil
	}
	return l.runStep(ctx, "Creating the HSE database", "initdb.log", 2*time.Minute, l.pgEnv(), l.data,
		l.pg("createdb"), "-O", dbUser, dbName)
}

// ---------------------------------------------------------------- readiness

func waitHTTP(ctx context.Context, url string, timeout time.Duration, ok func(*http.Response) bool, died func() bool) error {
	client := &http.Client{Timeout: 10 * time.Second, Transport: &http.Transport{Proxy: nil}}
	deadline := time.Now().Add(timeout)
	for {
		req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		resp, err := client.Do(req)
		if err == nil {
			good := ok(resp)
			_, _ = io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			if good {
				return nil
			}
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if died() {
			return errors.New("the process stopped")
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("no answer from %s after %s", url, timeout)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Second):
		}
	}
}

// ---------------------------------------------------------------- state and stop requests

type state struct {
	PID     int    `json:"pid"`
	URL     string `json:"url"`
	Status  string `json:"status"`
	Version string `json:"version"`
}

func (l *launcher) writeState(status string) {
	b, _ := json.MarshalIndent(state{os.Getpid(), l.url(), status, version}, "", "  ")
	_ = writeFileAtomic(l.path("run", "state.json"), b)
}

func (l *launcher) url() string { return fmt.Sprintf("http://127.0.0.1:%d", l.webPort) }

func (l *launcher) requestStop() int {
	stopFile := l.path("run", "stop")
	if !fileExists(l.path("run")) {
		fmt.Println("Not running (no data folder).")
		return 0
	}
	if lk, err := acquireLock(l.path("run", "launcher.lock")); err == nil {
		lk.release()
		fmt.Println("Not running.")
		return 0
	}
	if err := os.WriteFile(stopFile, []byte("stop\n"), 0o644); err != nil {
		fmt.Println("Cannot ask the launcher to stop:", err)
		return 1
	}
	for i := 0; i < 120; i++ {
		time.Sleep(time.Second)
		if lk, err := acquireLock(l.path("run", "launcher.lock")); err == nil {
			lk.release()
			fmt.Println("Stopped.")
			return 0
		}
	}
	fmt.Println("The launcher did not stop within 2 minutes.")
	return 1
}

// ---------------------------------------------------------------- main flow

func (l *launcher) checkBundle() error {
	if runtime.GOOS == "windows" && strings.Contains(strings.ToLower(l.root), `\appdata\local\temp\`) &&
		!fileExists(l.pg("pg_ctl")) {
		return errors.New("HSE.exe was started from inside the zip file.\n" +
			"Right-click the downloaded zip, choose \"Extract All...\", extract it to your Desktop or Documents,\n" +
			"then open the extracted \"HSE Platform\" folder and double-click HSE.exe there.")
	}
	need := []string{l.pg("pg_ctl"), l.pg("initdb"), l.pg("psql"), l.pg("postgres"), l.python, l.node,
		filepath.Join(l.backendDir, "alembic.ini"), l.webServer}
	for _, p := range need {
		if !fileExists(p) {
			return fmt.Errorf("A file of the platform is missing: %s\n"+
				"Extract the whole zip again (all folders next to HSE.exe are needed).", p)
		}
	}
	return nil
}

func (l *launcher) prepareDataDir() error {
	for _, d := range []string{"", "logs", "config", "run", "uploads"} {
		if err := os.MkdirAll(l.path(d), 0o755); err != nil {
			return fmt.Errorf("Cannot create the data folder %s: %v\n"+
				"Move the \"HSE Platform\" folder to your Desktop or Documents (a folder you can write to) and try again.", l.path(d), err)
		}
	}
	probe := l.path("run", "write-test.tmp")
	if err := os.WriteFile(probe, []byte("ok"), 0o644); err != nil {
		return fmt.Errorf("The data folder %s is not writable: %v\n"+
			"Move the \"HSE Platform\" folder to your Desktop or Documents and try again.", l.data, err)
	}
	_ = os.Remove(probe)
	if !fileExists(l.path("config", "settings.env")) {
		_ = os.WriteFile(l.path("config", "settings.env"), []byte(strings.ReplaceAll(settingsTemplate, "\n", lineEnd)), 0o644)
	}
	return nil
}

func (l *launcher) run() error {
	setTitle("HSE Platform")
	disableQuickEdit()
	fmt.Println()
	fmt.Println("  HSE Platform - portable edition " + version)
	fmt.Println("  ==============================================")
	fmt.Println()
	if err := l.checkBundle(); err != nil {
		return err
	}
	if err := l.prepareDataDir(); err != nil {
		return err
	}
	lock, err := acquireLock(l.path("run", "launcher.lock"))
	if err != nil {
		return l.alreadyRunning()
	}
	defer lock.release()
	_ = os.Remove(l.path("run", "stop"))
	rotateLogs(l.path("logs"))
	if l.logFile, err = os.OpenFile(l.path("logs", "launcher.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644); err != nil {
		return err
	}
	defer l.logFile.Close()
	l.logf("==== HSE.exe %s starting (pid %d) in %s, data %s", version, os.Getpid(), l.root, l.data)
	if err := killChildrenWithMe(); err != nil {
		l.logf("job object not available: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	go func() {
		s := <-sig
		l.logf("signal %v: stopping", s)
		cancel()
	}()
	go func() {
		for ctx.Err() == nil {
			if fileExists(l.path("run", "stop")) {
				_ = os.Remove(l.path("run", "stop"))
				l.logf("stop requested (HSE.exe --stop)")
				cancel()
				return
			}
			time.Sleep(time.Second)
		}
	}()

	runErr := l.startAll(ctx)
	if runErr == nil {
		select {
		case <-ctx.Done():
		case runErr = <-l.fatal:
		}
	}
	if errors.Is(runErr, context.Canceled) {
		runErr = nil
	}
	fmt.Println()
	l.say("Stopping the platform ...")
	l.writeState("stopping")
	l.shutdown()
	_ = os.Remove(l.path("run", "state.json"))
	l.say("Stopped. All data is kept in %s", l.data)
	l.logf("==== HSE.exe stopped")
	return runErr
}

func (l *launcher) alreadyRunning() error {
	b, err := os.ReadFile(l.path("run", "state.json"))
	var st state
	if err == nil && json.Unmarshal(b, &st) == nil && st.URL != "" {
		fmt.Println("  The HSE platform is already running from this folder (see its other window).")
		fmt.Println("  Address: " + st.URL)
		if !l.noBrowser && st.Status == "running" {
			openBrowser(st.URL + "/")
			fmt.Println("  Your browser has been opened.")
		}
		time.Sleep(4 * time.Second)
		os.Exit(0)
	}
	return errors.New("The HSE platform is already starting or stopping from this folder (another HSE window is open).\n" +
		"Wait a moment, or close the other window, then try again.")
}

func (l *launcher) startAll(ctx context.Context) error {
	firstStart := !fileExists(l.path("pgdata", "PG_VERSION"))
	if firstStart {
		l.say("First start: the database and the demo data are prepared once.")
		l.say("This takes a few minutes. Later starts take less than a minute.")
		fmt.Println()
	}
	if err := l.loadSecrets(); err != nil {
		return err
	}

	l.say("[1/6] Checking the ports ...")
	if !firstStart && l.pgRunning() {
		l.say("      A database server from an earlier run is still active; stopping it first.")
		l.stopPostgres()
	}
	if !portFree(l.pgPort) {
		return busyPortError(l.pgPort, "database")
	}
	if !portFree(l.apiPort) {
		return busyPortError(l.apiPort, "API")
	}
	var err error
	if l.webPort, err = l.pickWebPort(); err != nil {
		return err
	}
	if l.webPort != l.wantWebPort {
		l.say("      Port %d is busy; the web page uses port %d instead.", l.wantWebPort, l.webPort)
	}
	l.writeState("starting")

	l.say("[2/6] Starting the database ...")
	if firstStart {
		if err := l.initCluster(ctx); err != nil {
			return err
		}
	}
	if err := l.startPostgres(ctx); err != nil {
		return err
	}
	if err := l.ensureDatabase(ctx); err != nil {
		return err
	}

	l.say("[3/6] Updating the database structure ...")
	benv := l.backendEnv()
	if err := l.runStep(ctx, "Updating the database (alembic upgrade head)", "migrate.log", 30*time.Minute,
		benv, l.backendDir, l.python, "-m", "alembic", "upgrade", "head"); err != nil {
		return err
	}

	seeded := l.path("config", "seeded")
	if fileExists(seeded) {
		l.say("[4/6] Demo data already loaded (skipping).")
	} else {
		l.say("[4/6] Loading the demo data (first start only, a few minutes) ...")
		if err := l.runStep(ctx, "Loading the demo data", "seed.log", 90*time.Minute,
			benv, l.backendDir, l.python, "-m", "app.seed"); err != nil {
			return err
		}
		_ = os.WriteFile(seeded, []byte(time.Now().Format(time.RFC3339)+" "+version+lineEnd), 0o644)
	}
	_ = os.WriteFile(l.path("config", "bundle-version"), []byte(version+lineEnd), 0o644)

	l.say("[5/6] Starting the API, the timed jobs and the web server ...")
	api := &service{name: "API", logName: "api.log", make: func() *exec.Cmd {
		return l.command(nil, l.backendEnv(), l.backendDir, l.python, "-m", "uvicorn", "app.main:app",
			"--host", "127.0.0.1", "--port", strconv.Itoa(l.apiPort), "--timeout-keep-alive", "75")
	}}
	sched := &service{name: "timed jobs", logName: "scheduler.log", make: func() *exec.Cmd {
		return l.command(nil, l.backendEnv(), l.backendDir, l.python, "-m", "app.scheduler")
	}}
	web := &service{name: "web server", logName: "web.log", make: func() *exec.Cmd {
		return l.command(nil, l.webEnv(), l.webDir, l.node, l.webServer)
	}}
	for _, s := range []*service{api, sched, web} {
		if err := l.startService(s); err != nil {
			return err
		}
		l.mu.Lock()
		l.services = append(l.services, s)
		l.mu.Unlock()
	}

	l.say("[6/6] Waiting for the platform to answer ...")
	apiURL := fmt.Sprintf("http://127.0.0.1:%d%s", l.apiPort, healthPath)
	if err := waitHTTP(ctx, apiURL, 3*time.Minute, func(r *http.Response) bool {
		var h struct{ Database string }
		return r.StatusCode == 200 && json.NewDecoder(r.Body).Decode(&h) == nil && h.Database == "ok"
	}, api.exited); err != nil {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return l.stepError("Starting the API", l.path("logs", "api.log"), err)
	}
	if err := waitHTTP(ctx, l.url()+loginPath, 3*time.Minute, func(r *http.Response) bool {
		return r.StatusCode == 200
	}, web.exited); err != nil {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		return l.stepError("Starting the web server", l.path("logs", "web.log"), err)
	}
	if sched.exited() {
		return l.stepError("Starting the timed jobs", l.path("logs", "scheduler.log"), errors.New("the process stopped"))
	}
	for _, s := range []*service{api, sched, web} {
		go l.supervise(ctx, s)
	}

	l.writeState("running")
	l.logf("running at %s", l.url())
	fmt.Println()
	fmt.Println("  ----------------------------------------------------------------")
	fmt.Println("   The platform is running:  " + l.url())
	fmt.Println()
	if !l.noBrowser {
		openBrowser(l.url() + "/")
		fmt.Println("   Your browser has been opened. If it did not open, copy the")
		fmt.Println("   address above into Edge or Chrome.")
	}
	fmt.Println("   Demo sign-in: hatem.shehri@example.com / " + seedPassword)
	fmt.Println()
	fmt.Println("   Keep this window open while you use the platform.")
	fmt.Println("   Close this window (or press Ctrl+C) to stop it.")
	fmt.Println("  ----------------------------------------------------------------")
	return nil
}

func (l *launcher) shutdown() {
	l.mu.Lock()
	svcs := append([]*service(nil), l.services...)
	l.mu.Unlock()
	// All at once (no open work to finish); then the database, cleanly.
	var wg sync.WaitGroup
	for _, s := range svcs {
		wg.Add(1)
		go func(s *service) { defer wg.Done(); s.stop() }(s)
	}
	wg.Wait()
	l.stopPostgres()
}
