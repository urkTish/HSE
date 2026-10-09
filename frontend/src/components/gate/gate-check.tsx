"use client";
/**
 * Gate check screen (GC-1 … GC-16). Runs outside the app shell so a gate-device session, which can
 * only call /gate-checks/*, never triggers other API calls. Results live in component state only and
 * are cleared after clear_after_seconds; nothing personal is cached (GC-7).
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, CameraOff, Check, CircleAlert, CircleCheck, Clock, Info, KeyRound, LogIn, LogOut, ShieldAlert, Truck, UserRound, Users, WifiOff, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { EquipmentCheckCardView } from "@/components/cert/check";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { MutationError } from "@/components/common/states";
import { LanguageSwitch } from "@/components/shell/language-switch";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Link } from "@/i18n/navigation";
import { ApiError, api, unwrap, type Schemas } from "@/lib/api/client";
import { DEFAULT_TIME_ZONE, formatDate, formatDateTime, type DateDisplayPrefs } from "@/lib/datetime";
import { cn } from "@/lib/utils";
import { GasStatusBadge, PermitStatusBadge } from "@/components/ptw/common";

type Ctx = Schemas["GateCallerContext"];
type Res = Schemas["GateCheckResponse"];
type Result = Schemas["GateResult"];
type Pairing = Schemas["GatePairing"];

const GATE_KEY = "hse.gate.selected";
const PROJECT_KEY = "hse.currentProjectId";

function readLocal(k: string): string | null {
  try {
    return window.localStorage.getItem(k);
  } catch {
    return null;
  }
}
function writeLocal(k: string, v: string): void {
  try {
    window.localStorage.setItem(k, v);
  } catch {
    // storage unavailable: the choice is simply not remembered
  }
}

function subscribeOnline(cb: () => void): () => void {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}
function useOnline(): boolean {
  return useSyncExternalStore(
    subscribeOnline,
    () => navigator.onLine,
    () => true,
  );
}

/** Verdict colours: solid fills with maximum contrast for bright sunlight. Colour is never the only signal. */
const TONE: Record<Result, string> = {
  GRANTED: "bg-verdict-granted text-verdict-granted-fg",
  GRANTED_WITH_WARNING: "bg-verdict-note text-verdict-note-fg",
  DENIED: "bg-verdict-denied text-verdict-denied-fg",
  PENDING_ESCORT: "bg-verdict-pending text-verdict-pending-fg",
  PENDING_DRIVER: "bg-verdict-pending text-verdict-pending-fg",
  PENDING_ESCORT_VEHICLE: "bg-verdict-pending text-verdict-pending-fg",
  EXIT_RECORDED: "bg-verdict-neutral text-verdict-neutral-fg",
  WAP_VIEW: "bg-verdict-neutral text-verdict-neutral-fg",
  PTW_VIEW: "bg-verdict-neutral text-verdict-neutral-fg",
};

/** Reason codes that are information only (no provider yet), shown as a calm note rather than a warning. */
const NOTE_CODES = new Set<string>(["HOOK_NOT_AVAILABLE"]);

function VerdictIcon({ result, className }: { result: Result; className?: string }) {
  if (result === "GRANTED") return <Check aria-hidden className={className} />;
  // Granted with a note is still an entry: a tick, not an exclamation mark (no alarm fatigue).
  if (result === "GRANTED_WITH_WARNING") return <CircleCheck aria-hidden className={className} />;
  if (result === "DENIED") return <X aria-hidden className={className} />;
  if (result.startsWith("PENDING")) return <Clock aria-hidden className={className} />;
  if (result === "EXIT_RECORDED") return <LogOut aria-hidden className={className} />;
  return <ShieldAlert aria-hidden className={className} />;
}

function usePrefs(): DateDisplayPrefs {
  const locale = useLocale() === "ar" ? "ar" : "en";
  return { locale, timeZone: DEFAULT_TIME_ZONE, showHijri: false, digits: "western", dateFormatEn: "DD MMM YYYY" };
}

export function GateCheckScreen() {
  const t = useTranslations("gate");
  const qc = useQueryClient();
  const online = useOnline();
  const [projectId] = useState<string | null>(() => (typeof window === "undefined" ? null : new URLSearchParams(window.location.search).get("project") || readLocal(PROJECT_KEY)));
  const ctx = useQuery({
    queryKey: ["gate-context", projectId],
    queryFn: () => unwrap(api.GET("/api/v1/gate-checks/context", { params: { query: projectId ? { project_id: projectId } : {} } })),
    retry: false,
    staleTime: 60_000,
    gcTime: 0,
  });
  const err = ctx.error instanceof ApiError ? ctx.error : null;
  const reload = useCallback(() => void qc.invalidateQueries({ queryKey: ["gate-context"] }), [qc]);

  let body: ReactNode;
  if (ctx.isLoading) body = <p className="p-6 text-center text-lg">{t("loading")}</p>;
  else if (err && err.status === 401) body = <SignIn revoked={err.code === "GATE_DEVICE_REVOKED"} onDone={reload} />;
  else if (err && err.code === "NETWORK_ERROR") body = <Offline onRetry={reload} />;
  else if (err) body = <Problem title={err.status === 403 ? t("noPermission") : t("loadFailed")} onRetry={reload} />;
  else if (ctx.data) body = <Scanner ctx={ctx.data} onSessionLost={reload} />;
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground" data-testid="gate-screen">
      {!online ? (
        <div role="alert" className="flex items-center justify-center gap-2 bg-verdict-denied px-4 py-3 text-center text-lg font-bold text-verdict-denied-fg" data-testid="gate-offline">
          <WifiOff aria-hidden className="size-6" />
          {t("offline")}
        </div>
      ) : null}
      {body}
    </div>
  );
}

function Header({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex items-center justify-between gap-2 border-b bg-surface px-3 py-2">
      <div className="min-w-0 truncate text-base font-semibold">{title}</div>
      <div className="flex shrink-0 items-center gap-1">
        {children}
        <LanguageSwitch />
        <ThemeToggle />
      </div>
    </header>
  );
}

function Offline({ onRetry }: { onRetry: () => void }) {
  const t = useTranslations("gate");
  return (
    <>
      <Header title={t("title")} />
      <div className="flex flex-1 flex-col items-center justify-center gap-4 bg-verdict-denied p-6 text-center text-verdict-denied-fg" role="alert" data-testid="gate-offline">
        <WifiOff aria-hidden className="size-16" />
        <p className="text-2xl font-bold">{t("offline")}</p>
        <Button size="lg" variant="outline" className="h-14 border-0 bg-surface px-8 text-lg text-foreground" onClick={onRetry}>
          {t("retry")}
        </Button>
      </div>
    </>
  );
}

function Problem({ title, onRetry }: { title: string; onRetry: () => void }) {
  const t = useTranslations("gate");
  return (
    <>
      <Header title={t("title")} />
      <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
        <ShieldAlert aria-hidden className="size-12 text-destructive" />
        <p className="text-xl font-semibold">{title}</p>
        <div className="flex gap-2">
          <Button size="lg" onClick={onRetry}>
            {t("retry")}
          </Button>
          <Button size="lg" variant="outline" asChild>
            <Link href="/">{t("backToApp")}</Link>
          </Button>
        </div>
      </div>
    </>
  );
}

/* ───────────────────────────── Sign in (user or device) ───────────────────────────── */

function SignIn({ revoked, onDone }: { revoked: boolean; onDone: () => void }) {
  const t = useTranslations("gate");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  async function login() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/gate-device/login", { body: { device_token: token.trim() } }));
      setToken("");
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Header title={t("title")} />
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 p-4">
        {revoked ? (
          <p role="alert" className="rounded-md bg-verdict-denied p-3 font-semibold text-verdict-denied-fg">
            {t("deviceRevoked")}
          </p>
        ) : null}
        <section className="flex flex-col gap-3 rounded-lg border bg-surface p-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <KeyRound aria-hidden className="size-5" />
            {t("deviceLogin")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("deviceLoginHint")}</p>
          <label htmlFor="gate-token" className="text-sm font-medium">
            {t("deviceToken")}
          </label>
          <Input
            id="gate-token"
            type="password"
            autoComplete="off"
            className="ltr h-12 text-base"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && token.trim().length >= 20) void login();
            }}
            data-testid="device-token-input"
          />
          <MutationError error={error} />
          <Button size="lg" className="h-12 text-base" disabled={busy || token.trim().length < 20} onClick={() => void login()} data-testid="device-login">
            {t("startDevice")}
          </Button>
        </section>
        <section className="flex flex-col gap-3 rounded-lg border bg-surface p-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <UserRound aria-hidden className="size-5" />
            {t("userLogin")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("userLoginHint")}</p>
          <Button size="lg" variant="outline" className="h-12 text-base" asChild>
            <Link href={{ pathname: "/login", query: { next: "/gate" } }} data-testid="user-login">
              <LogIn aria-hidden />
              {t("signIn")}
            </Link>
          </Button>
        </section>
      </main>
    </>
  );
}

/* ───────────────────────────── Scanner ───────────────────────────── */

type Shown = { res: Res; clearAt: number | null };

function Scanner({ ctx, onSessionLost }: { ctx: Ctx; onSessionLost: () => void }) {
  const t = useTranslations("gate");
  const te = useTranslations("enums");
  const locale = useLocale();
  const isDevice = ctx.caller_kind === "device";
  const activeGates = ctx.gates.filter((g) => g.status === "active");
  const [gateId, setGateId] = useState<string>(() => {
    const wanted = (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("gate")) || readLocal(GATE_KEY);
    return activeGates.find((g) => g.id === wanted)?.id ?? activeGates[0]?.id ?? "";
  });
  const gate = activeGates.find((g) => g.id === gateId) ?? null;
  const [zoneId, setZoneId] = useState<string>("");
  const zone = gate && gate.protected_zones.length > 1 ? (gate.protected_zones.find((z) => z.id === zoneId)?.id ?? gate.protected_zones[0]?.id ?? "") : (gate?.protected_zones[0]?.id ?? "");
  const [direction, setDirection] = useState<Schemas["GateDirection"]>("in");
  const [manual, setManual] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [pairOutcome, setPairOutcome] = useState<Schemas["PairingRead"] | null>(null);
  const [holdClear, setHoldClear] = useState(false);
  const [camera, setCamera] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  // The thumb bar is fixed; the page reserves its measured height so nothing hides behind it.
  const [bar, setBar] = useState<HTMLDivElement | null>(null);
  const [slot, setSlot] = useState<HTMLDivElement | null>(null);
  const [barH, setBarH] = useState(224);
  useEffect(() => {
    if (!bar || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setBarH(bar.getBoundingClientRect().height));
    ro.observe(bar);
    return () => ro.disconnect();
  }, [bar]);
  const clearSeconds = ctx.clear_after_seconds;
  const name = (en: string, ar: string | null | undefined) => (locale === "ar" && ar ? ar : en);

  const reset = useCallback(() => {
    setShown(null);
    setPairOutcome(null);
    setError(null);
  }, []);

  const submit = useCallback(
    async (input: { payload?: string; printed_ref?: string }) => {
      if (!gate || busy) return;
      setBusy(true);
      setError(null);
      try {
        const res = await unwrap(
          api.POST("/api/v1/gate-checks", {
            body: {
              gate_id: gate.id,
              payload: input.payload ?? null,
              printed_ref: input.printed_ref ?? null,
              direction,
              zone_id: zone || null,
              pairing_id: pairing?.pairing_id ?? null,
            },
          }),
        );
        const waiting = res.pairing && res.pairing.state === "waiting" ? res.pairing : null;
        setPairing(waiting);
        setPairOutcome(null);
        setShown({ res, clearAt: waiting ? null : Date.now() + (res.clear_after_seconds || clearSeconds) * 1000 });
        setNow(Date.now());
        setManual("");
      } catch (e) {
        const ae = e instanceof ApiError ? e : new ApiError(0, null, "NETWORK_ERROR");
        if (ae.status === 401) onSessionLost();
        setError(ae);
      } finally {
        setBusy(false);
      }
    },
    [gate, busy, direction, zone, pairing, clearSeconds, onSessionLost],
  );

  // Test hook: e2e feeds a QR payload as if the camera had read it (the camera itself is never driven in tests).
  const submitRef = useRef(submit);
  useEffect(() => {
    submitRef.current = submit;
  }, [submit]);
  useEffect(() => {
    const w = window as unknown as { __hseGateScan?: (payload: string) => Promise<void> };
    w.__hseGateScan = (payload: string) => submitRef.current({ payload });
    return () => {
      delete w.__hseGateScan;
    };
  }, []);

  // One clock for the auto-clear and pairing countdowns.
  const ticking = Boolean(shown) || Boolean(pairing);
  useEffect(() => {
    if (!ticking) return;
    const h = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(h);
  }, [ticking]);

  // Auto-clear the result screen (GC-7), unless the guard is recording an admission.
  useEffect(() => {
    if (!shown?.clearAt || holdClear || pairing) return;
    const ms = shown.clearAt - Date.now();
    const h = window.setTimeout(reset, Math.max(ms, 0));
    return () => window.clearTimeout(h);
  }, [shown, holdClear, pairing, reset]);

  // Poll the pending pairing; the server finalises it on timeout (GC-8/9).
  const pairingId = pairing?.pairing_id ?? null;
  useEffect(() => {
    if (!pairingId) return;
    let live = true;
    const poll = async () => {
      try {
        const r = await unwrap(api.GET("/api/v1/gate-checks/pairings/{pairing_id}", { params: { path: { pairing_id: pairingId } } }));
        if (!live) return;
        if (r.pairing.state !== "waiting") {
          setPairing(null);
          setPairOutcome(r);
          setShown((s) => (s ? { ...s, clearAt: Date.now() + clearSeconds * 1000 } : s));
        }
      } catch {
        // transient: keep polling until the pairing expires
      }
    };
    const h = window.setInterval(() => void poll(), 2000);
    return () => {
      live = false;
      window.clearInterval(h);
    };
  }, [pairingId, clearSeconds]);

  async function cancelPairing() {
    if (!pairing) return;
    try {
      const r = await unwrap(api.POST("/api/v1/gate-checks/pairings/{pairing_id}/cancel", { params: { path: { pairing_id: pairing.pairing_id } } }));
      setPairOutcome(r);
    } catch {
      // the pairing may already be finished; clear locally either way
    }
    setPairing(null);
    setShown((s) => (s ? { ...s, clearAt: Date.now() + clearSeconds * 1000 } : s));
  }

  async function logoutDevice() {
    try {
      await unwrap(api.POST("/api/v1/gate-device/logout"));
    } catch {
      // ignore: the session is dropped locally anyway
    }
    onSessionLost();
  }

  if (!gate) {
    return (
      <>
        <Header title={t("title")} />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <p className="text-lg font-semibold">{t("noGates")}</p>
          {!isDevice ? (
            <Button variant="outline" asChild>
              <Link href="/">{t("backToApp")}</Link>
            </Button>
          ) : null}
        </div>
      </>
    );
  }

  const remaining = (at: number | null) => (at ? Math.max(0, Math.ceil((at - now) / 1000)) : null);
  const pairLeft = pairing ? remaining(new Date(pairing.expires_at).getTime()) : null;
  const clearLeft = shown && !pairing ? remaining(shown.clearAt) : null;

  return (
    <>
      <Header
        title={
          <span className="flex flex-col leading-tight">
            <span className="ltr" data-testid="gate-code">
              {gate.gate_code}
            </span>
            <span className="truncate text-xs font-normal text-muted-foreground">{name(gate.name_en, gate.name_ar)}</span>
          </span>
        }
      >
        {isDevice ? (
          <Button variant="ghost" size="sm" onClick={() => void logoutDevice()} data-testid="device-logout" aria-label={t("endDevice")}>
            <LogOut aria-hidden />
          </Button>
        ) : (
          <Button variant="ghost" size="sm" asChild>
            <Link href="/">{t("backToApp")}</Link>
          </Button>
        )}
      </Header>

      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-3 p-3" style={{ paddingBottom: barH + 16 }}>
        {/* Gate and zone pickers only before a scan: while a verdict is up it owns the screen (it repeats gate · zone). */}
        {!shown && !isDevice && activeGates.length > 1 ? (
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("gate")}
            <select
              className="h-12 rounded-md border bg-surface px-3 text-base"
              value={gate.id}
              onChange={(e) => {
                setGateId(e.target.value);
                writeLocal(GATE_KEY, e.target.value);
                setPairing(null);
                reset();
              }}
              data-testid="gate-select"
            >
              {activeGates.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.gate_code} — {name(g.name_en, g.name_ar)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {shown ? null : gate.protected_zones.length > 1 ? (
          <label className="flex flex-col gap-1 text-sm font-medium">
            {t("zone")}
            <select className="h-12 rounded-md border bg-surface px-3 text-base" value={zone} onChange={(e) => setZoneId(e.target.value)} data-testid="zone-select">
              {gate.protected_zones.map((z) => (
                <option key={z.id} value={z.id}>
                  {z.code} — {name(z.name_en, z.name_ar)}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="text-sm text-muted-foreground">
            {t("zone")}: <span className="ltr font-medium text-foreground">{gate.protected_zones[0]?.code ?? t("wholeSite")}</span>
          </p>
        )}

        {error ? (
          <div role="alert" className={cn("rounded-lg p-4 text-lg font-bold", error.code === "NETWORK_ERROR" ? "bg-verdict-denied text-verdict-denied-fg" : "border-2 border-danger bg-danger-bg text-danger")} data-testid="gate-error">
            {error.code === "NETWORK_ERROR" ? (
              <span className="flex items-center gap-2">
                <WifiOff aria-hidden className="size-6" />
                {t("offline")}
              </span>
            ) : error.code === "GATE_RATE_LIMITED" ? (
              t("rateLimited")
            ) : (
              (locale === "ar" && error.messageAr) || error.message
            )}
          </div>
        ) : null}

        {shown ? (
          <ResultView
            res={shown.res}
            pairing={pairing}
            pairLeft={pairLeft}
            pairOutcome={pairOutcome}
            clearLeft={clearLeft}
            onCancelPairing={() => void cancelPairing()}
            onClear={() => {
              setPairing(null);
              reset();
            }}
            onHold={setHoldClear}
            actionSlot={slot}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center text-muted-foreground" data-testid="gate-ready">
            <Camera aria-hidden className="size-10" />
            <p className="text-lg font-medium text-foreground">{t("ready")}</p>
            <p className="text-sm">{t("readyHint")}</p>
          </div>
        )}
      </main>

      {/* Thumb zone: everything the guard needs is at the bottom of the screen. */}
      <div ref={setBar} className="fixed inset-x-0 bottom-0 z-20 border-t bg-surface/95 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-lg backdrop-blur">
        <div className="mx-auto flex max-w-xl flex-col gap-2">
          {/* Result actions (next scan, cancel pairing, admitted despite denial) are portalled here: always in thumb reach. */}
          <div ref={setSlot} className="flex flex-col gap-2 empty:hidden" />
          {camera ? <CameraScanner onResult={(p) => void submit({ payload: p })} onClose={() => setCamera(false)} paused={busy || Boolean(shown && !pairing)} /> : null}
          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={t("direction")}>
            {(["in", "out"] as const).map((d) => (
              <button
                key={d}
                type="button"
                role="radio"
                aria-checked={direction === d}
                onClick={() => setDirection(d)}
                className={cn(
                  "inline-flex h-12 items-center justify-center gap-2 rounded-md border-2 text-base font-semibold",
                  direction === d ? "border-primary bg-primary text-primary-foreground" : "border-input bg-background text-muted-foreground",
                )}
                data-testid={`direction-${d}`}
              >
                {d === "in" ? <LogIn aria-hidden className="size-5 rtl:-scale-x-100" /> : <LogOut aria-hidden className="size-5 rtl:-scale-x-100" />}
                {te(`gateDirection.${d}`)}
                {direction === d ? <Check aria-hidden className="size-4" /> : null}
              </button>
            ))}
          </div>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (manual.trim()) void submit({ printed_ref: manual.trim().toUpperCase() });
            }}
          >
            <Input
              aria-label={t("printedRef")}
              placeholder={t("printedRef")}
              className="ltr h-12 flex-1 text-base uppercase"
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              autoComplete="off"
              autoCapitalize="characters"
              data-testid="manual-ref"
            />
            <Button type="submit" size="lg" className="h-12 px-5 text-base" disabled={busy || !manual.trim()} data-testid="manual-check">
              {t("check")}
            </Button>
          </form>
          <Button size="lg" className="h-14 text-lg" variant={camera ? "outline" : "default"} onClick={() => setCamera((c) => !c)} data-testid="toggle-camera">
            {camera ? <CameraOff aria-hidden /> : <Camera aria-hidden />}
            {camera ? t("stopCamera") : pairing ? t("scanPartner") : t("scan")}
          </Button>
        </div>
      </div>
    </>
  );
}

/* ───────────────────────────── Camera (zxing) ───────────────────────────── */

export function CameraScanner({ onResult, onClose, paused }: { onResult: (payload: string) => void; onClose: () => void; paused: boolean }) {
  const t = useTranslations("gate");
  const videoRef = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const cb = useRef({ onResult, paused, last: "", lastAt: 0 });
  useEffect(() => {
    cb.current.onResult = onResult;
    cb.current.paused = paused;
  }, [onResult, paused]);
  useEffect(() => {
    let stop: (() => void) | null = null;
    let live = true;
    (async () => {
      try {
        const { BrowserQRCodeReader } = await import("@zxing/browser");
        const reader = new BrowserQRCodeReader();
        if (!videoRef.current || !live) return;
        const controls = await reader.decodeFromConstraints({ video: { facingMode: "environment" } }, videoRef.current, (result) => {
          if (!result) return;
          const text = result.getText();
          const c = cb.current;
          // Ignore the same code read repeatedly while the result is on screen.
          if (c.paused || (text === c.last && Date.now() - c.lastAt < 5000)) return;
          c.last = text;
          c.lastAt = Date.now();
          c.onResult(text);
        });
        if (!live) controls.stop();
        else stop = () => controls.stop();
      } catch {
        if (live) setFailed(true);
      }
    })();
    return () => {
      live = false;
      stop?.();
    };
  }, []);
  return (
    <div className="relative overflow-hidden rounded-lg bg-black" data-testid="camera">
      {failed ? (
        <p className="p-4 text-center text-white">{t("cameraFailed")}</p>
      ) : (
        <video ref={videoRef} className="aspect-video w-full object-cover" muted playsInline aria-label={t("cameraView")} />
      )}
      <button type="button" onClick={onClose} className="absolute end-2 top-2 flex size-11 items-center justify-center rounded-full bg-black/60 text-white" aria-label={t("stopCamera")}>
        <X aria-hidden className="size-5" />
      </button>
    </div>
  );
}

/* ───────────────────────────── Result ───────────────────────────── */

function ResultView({
  res,
  pairing,
  pairLeft,
  pairOutcome,
  clearLeft,
  onCancelPairing,
  onClear,
  onHold,
  actionSlot,
}: {
  res: Res;
  pairing: Pairing | null;
  pairLeft: number | null;
  pairOutcome: Schemas["PairingRead"] | null;
  clearLeft: number | null;
  onCancelPairing: () => void;
  onClear: () => void;
  onHold: (v: boolean) => void;
  actionSlot: HTMLElement | null;
}) {
  const t = useTranslations("gate");
  const te = useTranslations("enums");
  const locale = useLocale();
  const [admit, setAdmit] = useState(false);
  const [admitted, setAdmitted] = useState(false);
  const pending = Boolean(pairing);
  const total = pairing ? Math.max(1, Math.round((new Date(pairing.expires_at).getTime() - new Date(res.occurred_at).getTime()) / 1000)) : 1;
  const withNote = res.result === "GRANTED_WITH_WARNING";
  // Deny reasons first, then warnings, then information-only notes (display order only).
  const rank = (r: Res["reasons"][number]) => (r.severity === "deny" ? 0 : NOTE_CODES.has(r.code) ? 2 : 1);
  const reasons = [...res.reasons].sort((a, b) => rank(a) - rank(b));
  return (
    <section className="flex flex-col gap-3" data-testid="gate-result" data-result={res.result} aria-live="assertive">
      <div
        className={cn("flex flex-col items-center gap-1 rounded-xl p-5 text-center shadow-md", TONE[res.result])}
        data-testid="verdict"
      >
        <VerdictIcon result={res.result} className="size-16 stroke-[3]" />
        {withNote ? (
          <>
            {/* "Granted" first and largest: the subject may enter; the note is secondary. */}
            <p className="text-5xl leading-none font-black tracking-tight uppercase sm:text-6xl">{te("gateResult.GRANTED")}</p>
            <p className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-black/10 px-3 py-0.5 text-base font-bold">
              <Info aria-hidden className="size-4" />
              {t("withNote")}
            </p>
          </>
        ) : (
          <p className="text-4xl leading-tight font-black tracking-tight uppercase sm:text-5xl">{te(`gateResult.${res.result}`)}</p>
        )}
        <p className="text-sm font-medium opacity-90">
          {te(`gateDirection.${res.direction}`)} · <span className="ltr">{res.gate.gate_code}</span>
          {res.zone ? (
            <>
              {" "}
              · <span className="ltr">{res.zone.code}</span>
            </>
          ) : null}
        </p>
        {res.late_exit ? (
          <p className="mt-1 inline-flex items-center gap-1.5 rounded bg-black/25 px-2 py-0.5 text-sm font-semibold">
            <Clock aria-hidden className="size-4" />
            {t("lateExit")}
          </p>
        ) : null}
        {pending && pairing ? (
          <div className="mt-2 w-full" data-testid="pairing">
            <p className="text-lg font-semibold">{t(`waitingFor.${pairing.waiting_for}`)}</p>
            <p className="text-5xl font-black tabular-nums" data-testid="pairing-countdown">
              {pairLeft}
              <span className="ms-1 text-xl font-semibold">{t("sec")}</span>
            </p>
            <div className="mt-2 h-2 w-full overflow-hidden rounded bg-white/30" aria-hidden>
              <div className="h-full bg-white transition-[width] duration-500" style={{ width: `${Math.min(100, ((pairLeft ?? 0) / total) * 100)}%` }} />
            </div>
          </div>
        ) : null}
      </div>

      {reasons.length ? (
        <ul className="flex flex-col gap-2" data-testid="reasons">
          {reasons.map((r, i) => {
            const note = r.severity !== "deny" && NOTE_CODES.has(r.code);
            return (
              <li
                key={`${r.code}-${i}`}
                className={cn(
                  "rounded-lg border-2 p-3 text-base font-medium",
                  r.severity === "deny" ? "border-danger bg-danger-bg text-foreground" : note ? "border-border bg-neutral-bg text-foreground" : "border-warning/60 bg-warning-bg text-foreground",
                )}
                data-code={r.code}
                data-severity={r.severity}
              >
                <span className="flex items-start gap-2">
                  {r.severity === "deny" ? (
                    <X aria-hidden className="mt-0.5 size-6 shrink-0 stroke-[3] text-danger" />
                  ) : note ? (
                    <Info aria-hidden className="mt-0.5 size-5 shrink-0 text-neutral" />
                  ) : (
                    <CircleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-warning" />
                  )}
                  <span className="min-w-0">
                    <span className="sr-only">{r.severity === "deny" ? t("reasonDeny") : note ? t("reasonNote") : t("reasonWarn")}: </span>
                    {locale === "ar" ? r.message_ar : r.message_en}
                    <span className="ltr block text-xs font-normal text-muted-foreground">{r.code}</span>
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}

      {res.person ? <PersonCard p={res.person} /> : null}
      {res.vehicle ? <VehicleCard v={res.vehicle} /> : null}
      {res.equipment ? <EquipmentCheckCardView c={res.equipment} /> : null}
      {res.wap ? <WapCard w={res.wap} /> : null}
      {res.permit ? <PermitCard w={res.permit} /> : null}

      {res.paired_results?.length ? <PairedList title={t("pairedResults")} items={res.paired_results} /> : null}
      {pairOutcome ? (
        <div data-testid="pairing-outcome" data-state={pairOutcome.pairing.state}>
          <p className="mb-1 text-base font-semibold">{t(`pairingState.${pairOutcome.pairing.state}`)}</p>
          {pairOutcome.results.length ? <PairedList title={t("pairedResults")} items={pairOutcome.results} /> : null}
        </div>
      ) : null}

      {actionSlot
        ? createPortal(
            <div className="flex gap-2">
              {pending ? (
                <Button size="lg" variant="outline" className="h-14 flex-1 border-2 text-lg" onClick={onCancelPairing} data-testid="cancel-pairing">
                  <X aria-hidden />
                  {t("cancelPairing")}
                </Button>
              ) : (
                <Button size="lg" variant="outline" className="relative h-14 flex-1 overflow-hidden border-2 text-lg" onClick={onClear} data-testid="next-scan">
                  <span className="flex flex-col items-center leading-tight">
                    {t("next")}
                    {clearLeft != null ? <span className="text-xs font-normal text-muted-foreground tabular-nums">{t("clearsIn", { s: clearLeft })}</span> : null}
                  </span>
                  {clearLeft != null ? (
                    <span aria-hidden className="absolute inset-x-0 bottom-0 h-1 bg-primary/70 transition-[width] duration-500 ease-linear" style={{ width: `${Math.min(100, (clearLeft / Math.max(1, res.clear_after_seconds || 30)) * 100)}%` }} />
                  ) : null}
                </Button>
              )}
              {res.result === "DENIED" && !admitted ? (
                <Button
                  size="lg"
                  variant="outline"
                  className="h-14 flex-1 border-2 border-danger px-3 text-base leading-tight whitespace-normal text-danger"
                  onClick={() => {
                    setAdmit(true);
                    onHold(true);
                  }}
                  data-testid="admitted-despite-denial"
                >
                  <ShieldAlert aria-hidden />
                  {t("admittedDespiteDenial")}
                </Button>
              ) : null}
            </div>,
            actionSlot,
          )
        : null}
      {admitted ? (
        <p role="status" className="flex items-start gap-2 rounded-lg border-2 border-danger bg-danger-bg p-3 font-semibold text-foreground" data-testid="admitted-recorded">
          <ShieldAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-danger" />
          {t("admittedRecorded")}
        </p>
      ) : null}
      {admit ? (
        <AdmitDialog
          checkId={res.check_id}
          onDone={() => setAdmitted(true)}
          onClose={() => {
            setAdmit(false);
            onHold(false);
          }}
        />
      ) : null}
    </section>
  );
}

function AdmitDialog({ checkId, onDone, onClose }: { checkId: string; onDone: () => void; onClose: () => void }) {
  const t = useTranslations("gate");
  const tc = useTranslations("common");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const ok = reason.trim().length >= 10;
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await unwrap(api.POST("/api/v1/gate-checks/{check_id}/admitted-despite-denial", { params: { path: { check_id: checkId } }, body: { reason: reason.trim() } }));
      onDone();
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent closeLabel={tc("close")}>
        <DialogHeader>
          <DialogTitle>{t("admittedDespiteDenial")}</DialogTitle>
          <DialogDescription>{t("admitHint")}</DialogDescription>
        </DialogHeader>
        <label htmlFor="admit-reason" className="text-sm font-medium">
          {t("admitReason")}
        </label>
        <Textarea id="admit-reason" rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="admit-reason" />
        <p className="text-xs text-muted-foreground">{t("min10")}</p>
        <MutationError error={error} />
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {tc("cancel")}
          </Button>
          <Button variant="destructive" disabled={!ok || busy} onClick={() => void save()} data-testid="admit-confirm">
            {t("recordAdmission")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CredLines({ lines }: { lines: Schemas["GateCredentialLine"][] }) {
  const t = useTranslations("gate");
  const te = useTranslations("enums");
  const locale = useLocale();
  const prefs = usePrefs();
  if (!lines.length) return null;
  return (
    <ul className="mt-3 flex flex-col divide-y rounded-md border" data-testid="credentials">
      {lines.map((c, i) => (
        <li key={`${c.kind}-${i}`} className="flex items-start gap-2 p-2 text-sm" data-ok={c.ok ? "true" : "false"}>
          {c.ok ? <Check aria-label={t("ok")} className="mt-0.5 size-5 shrink-0 text-success" /> : <X aria-label={t("notOk")} className="mt-0.5 size-5 shrink-0 text-danger" />}
          <span className="flex-1">
            <span className="font-semibold">{locale === "ar" ? c.label_ar : c.label_en}</span>
            <span className="block text-muted-foreground">
              {c.valid_until ? t("validUntil", { date: formatDate(c.valid_until, prefs) }) : null}
              {c.card_colour ? <> · {te(`cardColour.${c.card_colour}`)}</> : null}
              {c.area_codes?.length ? (
                <>
                  {" "}
                  · <span className="ltr">{c.area_codes.join(" ")}</span>
                </>
              ) : null}
              {c.adp_category ? <> · {te(`areaCategory.${c.adp_category}`)}</> : null}
              {c.window_today ? (
                <>
                  {" "}
                  · {t("today")} <span className="ltr">{c.window_today}</span>
                </>
              ) : null}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function PersonCard({ p }: { p: Schemas["GatePersonCard"] }) {
  const t = useTranslations("gate");
  const te = useTranslations("enums");
  return (
    <article className="rounded-xl border bg-surface p-3" data-testid="person-card">
      <div className="flex gap-3">
        <div className="size-28 shrink-0 overflow-hidden rounded-lg border bg-muted">
          {p.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL, never cached
            <img src={p.photo_url} alt={p.full_name_en} className="size-full object-cover" referrerPolicy="no-referrer" />
          ) : (
            <div className="flex size-full items-center justify-center text-muted-foreground">
              <UserRound aria-hidden className="size-12" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xl leading-tight font-bold" lang="en" dir="ltr">
            {p.full_name_en}
          </p>
          <p className="text-xl leading-tight font-bold" lang="ar" dir="rtl">
            {p.full_name_ar}
          </p>
          <p className="ltr mt-1 font-mono text-base">{p.worker_no}</p>
          <p className="text-sm text-muted-foreground">
            {p.employer_short_code ? <span className="ltr">{p.employer_short_code}</span> : null}
            {p.trade ? <> · {te(`trade.${p.trade}`)}</> : null}
          </p>
          {p.escort_required ? (
            <p className="mt-1 inline-flex items-center gap-1.5 rounded bg-verdict-pending px-2 py-0.5 text-sm font-bold text-verdict-pending-fg" data-testid="escort-required">
              <Users aria-hidden className="size-4 shrink-0" />
              {t("escortRequired")}
            </p>
          ) : null}
        </div>
      </div>
      <CredLines lines={p.credentials} />
    </article>
  );
}

function VehicleCard({ v }: { v: Schemas["GateVehicleCard"] }) {
  const t = useTranslations("gate");
  return (
    <article className="rounded-xl border bg-surface p-3" data-testid="vehicle-card">
      <div className="flex items-start gap-3">
        <Truck aria-hidden className="size-10 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="ltr text-xl font-bold">{v.vehicle_no}</p>
          <p className="text-sm text-muted-foreground">
            {t("fleetNo")} <span className="ltr">{v.fleet_no}</span> · {v.category}
          </p>
          {v.plate_display ? (
            <p className="mt-1 inline-block rounded border-2 px-2 text-lg font-bold">
              <bdi>{v.plate_display}</bdi>
            </p>
          ) : null}
          <p className="text-sm">{t("maxHeight", { m: v.max_working_height_m_agl })}</p>
        </div>
      </div>
      <CredLines lines={v.credentials} />
    </article>
  );
}

function WapCard({ w }: { w: Schemas["GateWapCard"] }) {
  const t = useTranslations("gate");
  const te = useTranslations("enums");
  const locale = useLocale();
  return (
    <article className="rounded-xl border bg-surface p-3" data-testid="wap-card">
      <p className="ltr text-xl font-bold">{w.wap_no}</p>
      <p className="text-sm">
        {te(`wapStatus.${w.status}`)} ·{" "}
        {w.in_window_now ? (
          <span className="inline-flex items-center gap-1 font-semibold text-success">
            <Check aria-hidden className="size-4" />
            {t("inWindow")}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 font-semibold text-danger">
            <X aria-hidden className="size-4" />
            {t("outsideWindow")}
          </span>
        )}
        {w.window_today ? (
          <>
            {" "}
            · {t("today")} <span className="ltr">{w.window_today}</span>
          </>
        ) : null}
      </p>
      {w.blockers.length ? (
        <ul className="mt-2 flex flex-wrap gap-1">
          {w.blockers.map((b) => (
            <li key={b} className="inline-flex items-center gap-1 rounded bg-verdict-denied px-2 py-0.5 text-xs font-semibold text-verdict-denied-fg">
              <X aria-hidden className="size-3.5" />
              {te(`wapBlocker.${b}`)}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-3 text-sm font-semibold">{t("crew", { n: w.crew.length })}</p>
      <ul className="mt-1 flex flex-col divide-y rounded-md border">
        {w.crew.map((c) => (
          <li key={c.worker_no} className="flex items-start gap-2 p-2 text-sm" data-eligible={c.eligible_now ? "true" : "false"}>
            {c.eligible_now ? <Check aria-label={t("ok")} className="size-5 shrink-0 text-success" /> : <X aria-label={t("notOk")} className="size-5 shrink-0 text-danger" />}
            <span className="flex-1">
              <span className="font-medium">{locale === "ar" ? c.full_name_ar : c.full_name_en}</span> <span className="ltr text-muted-foreground">{c.worker_no}</span>
              <span className="block text-xs text-muted-foreground">
                {te(`crewRole.${c.crew_role as Schemas["CrewRole"]}`)}
                {c.reasons.length ? <span className="ltr"> · {c.reasons.join(", ")}</span> : null}
              </span>
            </span>
          </li>
        ))}
      </ul>
      {w.vehicles.length ? (
        <p className="mt-2 text-sm">
          {t("vehicles")}: <span className="ltr">{w.vehicles.join(", ")}</span>
        </p>
      ) : null}
    </article>
  );
}

function PermitCard({ w }: { w: Schemas["GatePermitCard"] }) {
  const t = useTranslations("gate");
  const te = useTranslations("enums");
  const locale = useLocale();
  const prefs = usePrefs();
  return (
    <article className="rounded-xl border bg-surface p-3" data-testid="permit-card" data-status={w.status}>
      <p className="ltr text-xl font-bold">{w.display_no}</p>
      <p className="mt-1 flex flex-wrap items-center gap-2 text-sm">
        <PermitStatusBadge status={w.status} />
        <span>{w.work_types.map((wt) => te(`permitType.${wt}`)).join(" · ")}</span>
      </p>
      <p className="mt-1 text-sm">
        {w.in_window_now ? (
          <span className="inline-flex items-center gap-1 font-semibold text-success">
            <Check aria-hidden className="size-4" />
            {t("inWindow")}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 font-semibold text-danger">
            <X aria-hidden className="size-4" />
            {t("outsideWindow")}
          </span>
        )}
        {w.window_today ? (
          <>
            {" "}
            · {t("today")} <span className="ltr">{w.window_today}</span>
          </>
        ) : null}
        {w.current_shift_no ? <> · {t("ptwShift", { n: w.current_shift_no })}</> : null}
      </p>
      <p className="text-sm">
        {/* Same date format as the rest of the gate screen; not forced LTR, so an Arabic date reads in order. */}
        {t("ptwValidTo")}: <bdi className="font-medium whitespace-nowrap">{formatDateTime(w.valid_to_at, prefs)}</bdi>
      </p>
      {w.gas_status !== "not_required" ? (
        <p className="mt-1">
          <GasStatusBadge status={w.gas_status} />
        </p>
      ) : null}
      {w.blockers.length ? (
        <ul className="mt-2 flex flex-wrap gap-1">
          {w.blockers.map((b) => (
            <li key={b} className="inline-flex items-center gap-1 rounded bg-verdict-denied px-2 py-0.5 text-xs font-semibold text-verdict-denied-fg">
              <X aria-hidden className="size-3.5" />
              {te(`permitBlocker.${b}`)}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="mt-3 text-sm font-semibold">{t("crew", { n: w.crew.length })}</p>
      {w.crew.length ? (
        <ul className="mt-1 flex flex-col divide-y rounded-md border">
          {w.crew.map((c) => (
            <li key={c.worker_no} className="flex items-start gap-2 p-2 text-sm" data-eligible={c.eligible_now ? "true" : "false"}>
              {c.eligible_now ? <Check aria-label={t("ok")} className="size-5 shrink-0 text-success" /> : <X aria-label={t("notOk")} className="size-5 shrink-0 text-danger" />}
              <span className="flex-1">
                <span className="font-medium">{locale === "ar" ? c.full_name_ar : c.full_name_en}</span> <span className="ltr text-muted-foreground">{c.worker_no}</span>
                <span className="block text-xs text-muted-foreground">
                  {te(`ptwCrewRole.${c.crew_role as Schemas["PtwCrewRole"]}`)}
                  {c.reasons.length ? <span className="ltr"> · {c.reasons.join(", ")}</span> : null}
                </span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

function PairedList({ title, items }: { title: string; items: Schemas["GatePairedResult"][] }) {
  const te = useTranslations("enums");
  const locale = useLocale();
  return (
    <div className="rounded-xl border bg-surface p-3" data-testid="paired-results">
      <p className="mb-2 text-sm font-semibold">{title}</p>
      <ul className="flex flex-col gap-2">
        {items.map((r) => (
          <li key={r.check_id} className="flex flex-col gap-1">
            <span className="flex items-center gap-2">
              <span className={cn("inline-flex items-center gap-1 rounded px-2 py-0.5 text-sm font-bold", TONE[r.result])} data-result={r.result}>
                <VerdictIcon result={r.result} className="size-4" />
                {te(`gateResult.${r.result}`)}
              </span>
              <span className="ltr font-medium">{r.display_ref}</span>
              <span className="text-xs text-muted-foreground">{te(`gateSubjectKind.${r.subject_kind}`)}</span>
            </span>
            {r.reasons.length ? <span className="text-sm text-muted-foreground">{r.reasons.map((x) => (locale === "ar" ? x.message_ar : x.message_en)).join(" · ")}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

