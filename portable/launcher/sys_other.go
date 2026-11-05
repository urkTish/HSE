//go:build !windows

// Non-Windows stubs: the launcher is built for Windows; these let it be tried on Linux too.
package main

import (
	"os"
	"os/exec"
	"syscall"
)

const lineEnd = "\n"

func killChildrenWithMe() error { return nil }

func hideWindow(cmd *exec.Cmd) { cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true} }

func setTitle(string) {}

func disableQuickEdit() {}

func openBrowser(url string) { _ = exec.Command("xdg-open", url).Start() }

type fileLock struct{ f *os.File }

func acquireLock(path string) (*fileLock, error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0o644)
	if err != nil {
		return nil, err
	}
	if err := syscall.Flock(int(f.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		f.Close()
		return nil, err
	}
	return &fileLock{f}, nil
}

func (l *fileLock) release() { _ = l.f.Close() }
