"""Windows-owned Word automation; no pywin32 cache or student code execution.

The fixed command is passed as UTF-16 to PowerShell. Paths are JSON data, never
interpolated into executable text. Nothing runs until PDF export is requested.
"""
from __future__ import annotations
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$stage = 'starting-word'
$step = 'loading-automation'
$word = $null
$opened = $null
$owned = $false
$wordPid = $null
$created = $null
$previousLinks = $null
$previousSecurity = $null
$previousAlerts = $null
$failureType = $null
$statusPath = $null
$result = 1

function Write-Status([bool]$failed = $false, [string]$code = 'unavailable', [string]$kind = '') {
    $data = @{
        stage = $stage; step = $step; backend = 'powershell-word'
        pid = $wordPid; owned = $owned; creationTimeTicks = $created
        failed = $failed; code = $code; errorType = $kind
    }
    $temp = $statusPath + '.tmp'
    [IO.File]::WriteAllText($temp, ($data | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
    if ([IO.File]::Exists($statusPath)) {
        [IO.File]::Replace($temp, $statusPath, $null)
    } else {
        [IO.File]::Move($temp, $statusPath)
    }
}

try {
    if ($env:RECORDLY_WORD_SELF_TEST -ne '1') {
        $requestPath = [IO.Path]::GetFullPath($env:RECORDLY_WORD_REQUEST)
        $request = [IO.File]::ReadAllText($requestPath) | ConvertFrom-Json
        $source = [IO.Path]::GetFullPath([string]$request.source)
        $target = [IO.Path]::GetFullPath([string]$request.target)
        $statusPath = [IO.Path]::ChangeExtension($requestPath, '.status.json')
        if (([IO.Path]::GetDirectoryName($source) -ne [IO.Path]::GetDirectoryName($requestPath)) -or
            ([IO.Path]::GetDirectoryName($source) -ne [IO.Path]::GetDirectoryName($target)) -or
            ([IO.Path]::GetExtension($source) -ne '.docx') -or
            ([IO.Path]::GetExtension($target) -ne '.pdf')) {
            throw [ArgumentException]::new('Invalid conversion paths.')
        }
        Write-Status
    }
    # Only this PDF subprocess compiles the tiny HWND-to-PID declaration.
    # No compiler, PowerShell or Word is started during Recordly startup.
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class RecordlyWordProcess {
    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
}
'@
    if ($env:RECORDLY_WORD_SELF_TEST -eq '1') {
        [uint32]$probe = 0
        [void][RecordlyWordProcess]::GetWindowThreadProcessId([IntPtr]::Zero, [ref]$probe)
        $ready = [Text.Encoding]::UTF8.GetBytes("RECORDLY_WORD_HELPER_READY`n")
        [Console]::OpenStandardOutput().Write($ready, 0, $ready.Length)
        exit 0
    }
    $existing = @(Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
    $started = [DateTime]::UtcNow
    $step = 'creating-word-instance'
    Write-Status
    $word = New-Object -ComObject Word.Application
    $step = 'configuring-word'
    Write-Status
    # Preserve application settings even if COM supplied an existing instance.
    # Never hide or quit an existing Word window.
    $previousAlerts = $word.DisplayAlerts
    $previousSecurity = $word.AutomationSecurity
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $previousLinks = $word.Options.UpdateLinksAtOpen
    $word.Options.UpdateLinksAtOpen = $false
    $stage = 'opening-document'
    $step = $stage
    Write-Status
    $missing = [Type]::Missing
    # Word's first 12 documented arguments: read-only, no recent-file entry,
    # no conversion dialog, no reverting user work and an invisible window.
    # UpdateLinks is an Excel argument, NOT a Word Documents.Open argument.
    $opened = $word.Documents.Open($source, $false, $true, $false,
        $missing, $missing, $false, $missing, $missing, $missing, $missing, $false)
    $step = 'checking-word-process'
    Write-Status
    try {
        # Hwnd belongs to Word.Window, not Word.Application. A document must
        # exist first; older Word versions may not expose this window property.
        [uint32]$nativePid = 0
        $documentWindow = $opened.Windows.Item(1)
        try {
            [void][RecordlyWordProcess]::GetWindowThreadProcessId(
                [IntPtr]([long]$documentWindow.Hwnd), [ref]$nativePid)
        } finally {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($documentWindow)
        }
        if ($nativePid -ne 0) {
            $wordPid = [int]$nativePid
            $wordProcess = Get-Process -Id $wordPid -ErrorAction Stop
            $createdAt = $wordProcess.StartTime.ToUniversalTime()
            $created = $createdAt.ToFileTimeUtc().ToString([Globalization.CultureInfo]::InvariantCulture)
            $owned = ($wordProcess.ProcessName -ieq 'WINWORD') -and
                     ($existing -notcontains $wordPid) -and ($createdAt -ge $started)
        }
    } catch {
        $owned = $false
    }
    # Unknown ownership never prevents read-only conversion, but it forbids
    # terminating that process. This also keeps older Office versions usable.
    if ($owned) { $word.Visible = $false }
    $stage = 'exporting-pdf'
    $step = $stage
    Write-Status
    $opened.ExportAsFixedFormat($target, 17, $false)
    $stage = 'pdf-written'
    Write-Status
    $result = 0
} catch {
    $errorObject = $_.Exception
    while ($null -ne $errorObject.InnerException) { $errorObject = $errorObject.InnerException }
    $code = '0x' + $errorObject.HResult.ToString('X8')
    $kind = $errorObject.GetType().Name
    $allowed = @('COMException', 'InvalidOperationException', 'ArgumentException',
        'IOException', 'FileNotFoundException', 'DirectoryNotFoundException',
        'UnauthorizedAccessException', 'NotSupportedException', 'RuntimeException')
    if ($failureType) { $kind = $failureType }
    elseif ($allowed -notcontains $kind) { $kind = 'Exception' }
    if ($statusPath) { Write-Status $true $code $kind }
} finally {
    if ($null -ne $opened) {
        try { $opened.Close(0) } catch {}
        try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($opened) } catch {}
    }
    if ($null -ne $word) {
        if ($null -ne $previousLinks) {
            try { $word.Options.UpdateLinksAtOpen = $previousLinks } catch {}
        }
        if ($null -ne $previousSecurity) {
            try { $word.AutomationSecurity = $previousSecurity } catch {}
        }
        if ($null -ne $previousAlerts) {
            try { $word.DisplayAlerts = $previousAlerts } catch {}
        }
    }
    if (($null -ne $word) -and $owned) {
        # Preserve any unrelated document opened into this instance meanwhile.
        try {
            if ($word.Documents.Count -eq 0) { $word.Quit(0) }
            else { $owned = $false; Write-Status ($result -ne 0) $code $kind }
        } catch {}
    }
    if ($null -ne $word) {
        try { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) } catch {}
    }
}
exit $result
"""

def _kernel32():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    kernel.GetDllDirectoryW.restype = wintypes.DWORD
    kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    kernel.SetDllDirectoryW.restype = wintypes.BOOL
    return kernel

def launch(request: Path | None = None, *, self_test: bool = False):
    env = os.environ.copy()
    env.pop("RECORDLY_WORD_SELF_TEST", None)
    env.pop("RECORDLY_WORD_REQUEST", None)
    if self_test:
        env["RECORDLY_WORD_SELF_TEST"] = "1"
    else:
        env["RECORDLY_WORD_REQUEST"] = str(request.resolve())
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        root = os.path.normcase(os.path.abspath(bundle))
        def outside_bundle(value):
            try:
                return os.path.commonpath([root, os.path.normcase(os.path.abspath(value))]) != root
            except ValueError:
                return True
        env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep) if p and outside_bundle(p))
    executable = Path(env.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-STA",
               "-EncodedCommand", base64.b64encode(SCRIPT.encode("utf-16le")).decode("ascii")]
    kernel = None
    previous = None
    if getattr(sys, "frozen", False):
        # PyInstaller documents that its private DLL directory is inherited by
        # external programs. Restore Windows' normal DLL lookup just for spawn.
        kernel = _kernel32()
        buffer = ctypes.create_unicode_buffer(32768)
        size = kernel.GetDllDirectoryW(len(buffer), buffer)
        if size >= len(buffer):
            raise OSError("Cannot inspect the worker DLL search path.")
        previous = buffer.value or None
        if not kernel.SetDllDirectoryW(None):
            raise OSError("Cannot isolate the Word helper DLL search path.")
    process = None
    try:
        process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE if self_test else subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return process
    finally:
        if kernel is not None:
            if not kernel.SetDllDirectoryW(previous):
                if process is not None:
                    process.kill()
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired: pass
                    if process.stdout is not None: process.stdout.close()
                raise OSError("Cannot restore the worker DLL search path.")

def terminate_owned_word(details: dict):
    """Pin an exact process handle and creation time; never taskkill by name/PID."""
    pid = details.get("pid")
    ticks = details.get("creationTimeTicks")
    if (details.get("owned") is not True or type(pid) is not int or pid <= 0 or
            not isinstance(ticks, str) or not ticks.isascii() or not ticks.isdigit() or len(ticks) > 19):
        return
    try:
        kernel = _kernel32()
        handle = kernel.OpenProcess(0x1000 | 0x0001 | 0x00100000, False, pid)
        if not handle:
            return
        try:
            created, exited, system, user = (wintypes.FILETIME() for _ in range(4))
            if kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                      ctypes.byref(system), ctypes.byref(user)):
                actual = (created.dwHighDateTime << 32) | created.dwLowDateTime
                if actual == int(ticks):
                    if kernel.TerminateProcess(handle, 1):
                        kernel.WaitForSingleObject(handle, 3000)
        finally:
            kernel.CloseHandle(handle)
    except (OSError, AttributeError, ValueError, OverflowError):
        pass  # Uncertain ownership is never permission to terminate Word.

def check_automation() -> int:
    """CI smoke check of the frozen helper, without requiring installed Word."""
    process = None
    try:
        process = launch(self_test=True)
        output, _ = process.communicate(timeout=30)
        ready = process.returncode == 0 and output.strip() == b"RECORDLY_WORD_HELPER_READY"
    except (OSError, subprocess.SubprocessError):
        if process is not None:
            process.kill()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: pass
        ready = False
    print(json.dumps({"status": "ready" if ready else "failed", "backend": "powershell-word",
                      "wordStarted": False}))
    return 0 if ready else 1
