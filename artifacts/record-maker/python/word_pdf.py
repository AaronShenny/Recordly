"""Bounded Word automation in an isolated helper, never the document worker."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from word_pdf_windows import launch, terminate_owned_word

TIMEOUT_SECONDS = 30
HELPER_STEPS = {
    "launching-helper", "loading-automation", "initializing-com",
    "creating-word-instance", "checking-word-process", "configuring-word", "opening-document", "exporting-pdf",
}
ERROR_TYPES = {
    "AttributeError", "TypeError", "ImportError", "ModuleNotFoundError",
    "FileNotFoundError", "PermissionError", "OSError", "RuntimeError", "com_error",
    "COMException", "InvalidOperationException", "ArgumentException", "IOException",
    "FileNotFoundException", "DirectoryNotFoundException", "UnauthorizedAccessException",
    "NotSupportedException", "RuntimeException", "WordOwnershipUncertain",
}

def _error_details(error: Exception) -> dict:
    """Capture fixed classifications, never exception messages or local paths."""
    code = getattr(error, "hresult", None)
    if not isinstance(code, int) or isinstance(code, bool):
        args = getattr(error, "args", ())
        code = args[0] if args and isinstance(args[0], int) and not isinstance(args[0], bool) else None
    details = {
        "code": f"0x{code & 0xffffffff:08X}" if isinstance(code, int) else "unavailable",
        "errorType": type(error).__name__ if type(error).__name__ in ERROR_TYPES else "Exception",
    }
    module = getattr(error, "name", None)
    if module in {"pythoncom", "pywintypes", "win32com", "win32com.client", "win32process", "win32api"}:
        details["dependency"] = module
    return details

def _status(filename: Path, **data):
    temporary = filename.with_suffix(".tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    temporary.replace(filename)

def run_helper(request_path: Path) -> int:
    """Legacy comparison CLI; normal PDF exports use the Windows helper."""
    request_path = request_path.resolve()
    data = json.loads(request_path.read_text(encoding="utf-8"))
    source = Path(data["source"]).resolve()
    target = Path(data["target"]).resolve()
    status = request_path.with_suffix(".status.json")
    if source.parent != request_path.parent or target.parent != source.parent or source.suffix.lower() != ".docx" or target.suffix.lower() != ".pdf":
        raise ValueError("Invalid Word conversion paths.")
    stage = "starting-word"
    word = opened = None
    pid = None
    owned = False
    creation_time = None
    previous_links = None
    pythoncom = None
    initialized = False
    step = "loading-automation"
    try:
        # Imports and COM initialization can fail in packaged builds too.
        # Record them before any Word operation rather than blaming Office.
        _status(status, stage=stage, step=step)
        import pythoncom
        from win32com.client import dynamic
        import win32process
        import win32api
        step = "initializing-com"
        _status(status, stage=stage, step=step)
        pythoncom.CoInitialize()
        initialized = True
        started = time.time()
        step = "creating-word-instance"
        _status(status, stage=stage, step=step)
        # Dynamic dispatch avoids broken/stale generated win32com caches.
        dispatch = pythoncom.CoCreateInstance(
            pythoncom.CLSIDFromProgID("Word.Application"), None,
            pythoncom.CLSCTX_LOCAL_SERVER, pythoncom.IID_IDispatch)
        word = dynamic.Dispatch(dispatch)
        step = "configuring-word"
        _status(status, stage=stage, step=step, pid=pid, owned=owned, creationTime=creation_time)
        word.Visible = False
        word.DisplayAlerts = 0
        word.AutomationSecurity = 3
        previous_links = word.Options.UpdateLinksAtOpen
        word.Options.UpdateLinksAtOpen = False
        stage = "opening-document"
        step = stage
        _status(status, stage=stage, step=step, pid=pid, owned=owned, creationTime=creation_time)
        opened = word.Documents.Open(str(source), ConfirmConversions=False,
            ReadOnly=True, AddToRecentFiles=False, Visible=False)
        try:
            # Word exposes Hwnd on its document Window, not Application.
            pid = win32process.GetWindowThreadProcessId(opened.Windows.Item(1).Hwnd)[1]
            handle = win32api.OpenProcess(0x0400, False, pid)
            try:
                creation_time = win32process.GetProcessTimes(handle)["CreationTime"].timestamp()
                owned = creation_time >= started
            finally:
                handle.Close()
        except Exception:
            owned = False  # Never terminate a process whose ownership is uncertain.
        stage = "exporting-pdf"
        step = stage
        _status(status, stage=stage, step=step, pid=pid, owned=owned, creationTime=creation_time)
        opened.ExportAsFixedFormat(str(target), 17, OpenAfterExport=False)
        _status(status, stage="pdf-written", pid=pid, owned=owned, creationTime=creation_time)
        return 0
    except Exception as error:
        _status(status, stage=stage, step=step, pid=pid, owned=owned,
                creationTime=creation_time, **_error_details(error), failed=True)
        return 1
    finally:
        if opened is not None:
            try:
                opened.Close(False)
            except Exception:
                pass
        # Only close a Word process demonstrably created for this helper.
        if word is not None and previous_links is not None:
            try:
                word.Options.UpdateLinksAtOpen = previous_links
            except Exception:
                pass
        if word is not None and owned:
            try:
                word.Quit()
            except Exception:
                pass
        if initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

def convert(source: Path) -> bytes:
    if sys.platform != "win32":
        raise ValueError("PDF export requires Microsoft Word on Windows. The DOCX version was retained.")
    source = source.resolve()
    target = source.with_suffix(".pdf")
    request = source.with_suffix(".word-request.json")
    status = request.with_suffix(".status.json")
    request.write_text(json.dumps({"source": str(source), "target": str(target)}), encoding="utf-8")
    target.unlink(missing_ok=True)
    _status(status, stage="starting-word", step="launching-helper", backend="powershell-word")
    process = None
    timed_out = False
    try:
        process = launch(request)
    except OSError as error:
        _status(status, stage="starting-word", step="launching-helper",
                backend="powershell-word", failed=True, **_error_details(error))
    if process is not None:
        try:
            process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
    try:
        details = json.loads(status.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    if timed_out:
        terminate_owned_word(details)
    if target.exists() and details.get("stage") == "pdf-written" and not details.get("failed"):
        raw = target.read_bytes()
        if raw.startswith(b"%PDF-") and b"%%EOF" in raw[-1024:]:
            return raw
    stage = details.get("stage", "starting-word")
    if stage not in {"starting-word", "opening-document", "exporting-pdf", "pdf-written"}:
        stage = "starting-word"
    code = details.get("code", "unavailable")
    if not isinstance(code, str) or len(code) != 10 or not code.startswith("0x") or any(c not in "0123456789ABCDEF" for c in code[2:]):
        code = "unavailable"
    step = details.get("step")
    if step not in HELPER_STEPS:
        step = "launching-helper" if not details else stage
    error_type = details.get("errorType")
    safe_details = f" Helper step: {step}."
    if details.get("backend") == "powershell-word":
        safe_details += " Automation backend: powershell-word."
    if error_type in ERROR_TYPES or error_type == "Exception":
        safe_details += f" Failure type: {error_type}."
    dependency = details.get("dependency")
    if dependency in {"pythoncom", "pywintypes", "win32com", "win32com.client", "win32process", "win32api"}:
        safe_details += f" Missing component: {dependency}."
    exit_code = getattr(process, "returncode", None)
    if isinstance(exit_code, int):
        safe_details += f" Helper exit: {exit_code}."
    if step == "loading-automation" or error_type in {"ImportError", "ModuleNotFoundError"}:
        advice = ("Recordly could not load its Word automation components. Reinstall the latest Recordly build "
                  "and share diagnostics if it continues; this does not establish an Office installation problem.")
    elif process is None:
        advice = ("Recordly could not start its Windows automation helper. Share Recordly diagnostics "
                  "and the installed app version; this does not establish an Office installation problem.")
    elif not details or step == "launching-helper":
        advice = ("The PDF helper exited before reporting its progress. Share Recordly diagnostics "
                  "and the installed app version; this does not establish an Office installation problem.")
    elif error_type == "WordOwnershipUncertain":
        advice = ("Recordly did not modify or close Word because instance ownership was uncertain. "
                  "Save and close Word, retry PDF export, then share diagnostics if it continues.")
    else:
        advice = ("Open desktop Word manually, finish activation or any dialogs, then retry PDF export. "
                  "If Word opens normally but export still fails, share Recordly diagnostics before repairing Office.")
    reason = "timed out after 30 seconds" if timed_out else "failed"
    raise ValueError(f"Microsoft Word PDF export {reason} during {stage} (Office code: {code}). "
                     f"The DOCX was retained.{safe_details} {advice}")
