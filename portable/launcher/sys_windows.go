//go:build windows

package main

import (
	"errors"
	"os/exec"
	"syscall"
	"unsafe"
)

const lineEnd = "\r\n"

var (
	kernel32                     = syscall.NewLazyDLL("kernel32.dll")
	shell32                      = syscall.NewLazyDLL("shell32.dll")
	procCreateJobObjectW         = kernel32.NewProc("CreateJobObjectW")
	procSetInformationJobObject  = kernel32.NewProc("SetInformationJobObject")
	procAssignProcessToJobObject = kernel32.NewProc("AssignProcessToJobObject")
	procSetConsoleTitleW         = kernel32.NewProc("SetConsoleTitleW")
	procGetConsoleMode           = kernel32.NewProc("GetConsoleMode")
	procSetConsoleMode           = kernel32.NewProc("SetConsoleMode")
	procShellExecuteW            = shell32.NewProc("ShellExecuteW")

	jobHandle uintptr // kept open for the life of the launcher
)

const (
	createNoWindow                  = 0x08000000
	jobObjectExtendedLimitInfo      = 9
	jobObjectLimitKillOnJobClose    = 0x2000
	jobObjectLimitSilentBreakawayOk = 0x1000
	enableQuickEditMode             = 0x0040
	enableExtendedFlags             = 0x0080
	errorSharingViolation           = syscall.Errno(32)
	errorLockViolation              = syscall.Errno(33)
)

type ioCounters struct {
	ReadOperationCount, WriteOperationCount, OtherOperationCount uint64
	ReadTransferCount, WriteTransferCount, OtherTransferCount    uint64
}

type jobBasicLimit struct {
	PerProcessUserTimeLimit int64
	PerJobUserTimeLimit     int64
	LimitFlags              uint32
	MinimumWorkingSetSize   uintptr
	MaximumWorkingSetSize   uintptr
	ActiveProcessLimit      uint32
	Affinity                uintptr
	PriorityClass           uint32
	SchedulingClass         uint32
}

type jobExtendedLimit struct {
	Basic                 jobBasicLimit
	IoInfo                ioCounters
	ProcessMemoryLimit    uintptr
	JobMemoryLimit        uintptr
	PeakProcessMemoryUsed uintptr
	PeakJobMemoryUsed     uintptr
}

// killChildrenWithMe puts the launcher in a job object that ends every process it started
// (API, jobs, web server, and PostgreSQL as a last resort) if the launcher itself is killed.
func killChildrenWithMe() error {
	h, _, err := procCreateJobObjectW.Call(0, 0)
	if h == 0 {
		return err
	}
	var info jobExtendedLimit
	info.Basic.LimitFlags = jobObjectLimitKillOnJobClose
	r, _, err := procSetInformationJobObject.Call(h, jobObjectExtendedLimitInfo,
		uintptr(unsafe.Pointer(&info)), unsafe.Sizeof(info))
	if r == 0 {
		syscall.CloseHandle(syscall.Handle(h))
		return err
	}
	self, _ := syscall.GetCurrentProcess()
	r, _, err = procAssignProcessToJobObject.Call(h, uintptr(self))
	if r == 0 {
		syscall.CloseHandle(syscall.Handle(h))
		return err
	}
	jobHandle = h
	return nil
}

// hideWindow runs a child without a console window of its own (its output goes to a log file),
// so console events of the launcher window reach only the launcher.
func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
}

func setTitle(t string) {
	p, err := syscall.UTF16PtrFromString(t)
	if err == nil {
		procSetConsoleTitleW.Call(uintptr(unsafe.Pointer(p)))
	}
}

// disableQuickEdit: a click in the console window would otherwise pause the launcher's output.
func disableQuickEdit() {
	h, err := syscall.GetStdHandle(syscall.STD_INPUT_HANDLE)
	if err != nil {
		return
	}
	var mode uint32
	if r, _, _ := procGetConsoleMode.Call(uintptr(h), uintptr(unsafe.Pointer(&mode))); r == 0 {
		return
	}
	procSetConsoleMode.Call(uintptr(h), uintptr((mode&^enableQuickEditMode)|enableExtendedFlags))
}

func openBrowser(url string) {
	verb, _ := syscall.UTF16PtrFromString("open")
	u, err := syscall.UTF16PtrFromString(url)
	if err != nil {
		return
	}
	procShellExecuteW.Call(0, uintptr(unsafe.Pointer(verb)), uintptr(unsafe.Pointer(u)), 0, 0, 1)
}

type fileLock struct{ h syscall.Handle }

// acquireLock opens the lock file without sharing: a second launcher on the same data folder fails.
func acquireLock(path string) (*fileLock, error) {
	p, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return nil, err
	}
	h, err := syscall.CreateFile(p, syscall.GENERIC_READ|syscall.GENERIC_WRITE, 0, nil,
		syscall.OPEN_ALWAYS, syscall.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		if errors.Is(err, errorSharingViolation) || errors.Is(err, errorLockViolation) {
			return nil, errors.New("locked")
		}
		return nil, err
	}
	return &fileLock{h}, nil
}

func (f *fileLock) release() { syscall.CloseHandle(f.h) }
