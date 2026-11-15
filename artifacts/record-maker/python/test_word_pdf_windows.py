import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import word_pdf
import word_pdf_windows as windows


class WindowsWordTests(unittest.TestCase):
    def test_launch_uses_only_fixed_windows_commands_and_keeps_paths_as_data(self):
        with tempfile.TemporaryDirectory() as folder:
            request = Path(folder) / "Unicode-\u03a9-'; injected.ps1.json"
            with patch.object(windows.subprocess, "Popen") as popen:
                windows.launch(request)
            args, kwargs = popen.call_args
            command = args[0]
            self.assertEqual(Path(command[0]).name, "powershell.exe")
            self.assertEqual(Path(command[0]).parent.name, "v1.0")
            self.assertNotIn("-ExecutionPolicy", command)
            self.assertNotIn("--word-pdf", command)
            script = base64.b64decode(command[-1]).decode("utf-16le")
            self.assertEqual(script, windows.SCRIPT)
            self.assertNotIn(str(request), script)
            self.assertEqual(kwargs["env"]["RECORDLY_WORD_REQUEST"], str(request.resolve()))
            self.assertNotIn("RECORDLY_WORD_SELF_TEST", kwargs["env"])
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertLess(sum(len(arg) + 3 for arg in command), 30000)
            self.assertNotIn("$word.Hwnd", script)

    def test_frozen_launch_sanitizes_then_restores_private_dll_lookup(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / "bundle"
            good = Path(folder) / "system"
            kernel = SimpleNamespace(GetDllDirectoryW=Mock(), SetDllDirectoryW=Mock(return_value=True))
            def directory(size, buffer):
                buffer.value = str(bundle)
                return len(str(bundle))
            kernel.GetDllDirectoryW.side_effect = directory
            with patch.object(windows.sys, "frozen", True, create=True), \
                 patch.object(windows.sys, "_MEIPASS", str(bundle), create=True), \
                 patch.object(windows, "_kernel32", return_value=kernel), \
                 patch.dict(os.environ, {"PATH": os.pathsep.join([str(bundle), str(bundle / "win32"), str(good)])}), \
                 patch.object(windows.subprocess, "Popen") as popen:
                windows.launch(Path(folder) / "request.json")
            self.assertEqual(popen.call_args.kwargs["env"]["PATH"], str(good))
            self.assertEqual(kernel.SetDllDirectoryW.call_args_list[0].args, (None,))
            self.assertEqual(kernel.SetDllDirectoryW.call_args_list[-1].args, (str(bundle),))

    def test_dll_lookup_is_restored_even_when_launch_fails(self):
        kernel = SimpleNamespace(GetDllDirectoryW=Mock(return_value=0), SetDllDirectoryW=Mock(return_value=True))
        with patch.object(windows.sys, "frozen", True, create=True), \
             patch.object(windows, "_kernel32", return_value=kernel), \
             patch.object(windows.subprocess, "Popen", side_effect=FileNotFoundError()):
            with self.assertRaises(FileNotFoundError):
                windows.launch(Path("request.json"))
        self.assertEqual(kernel.SetDllDirectoryW.call_count, 2)

    def test_cleanup_never_opens_an_unowned_or_malformed_process(self):
        with patch.object(windows, "_kernel32") as kernel:
            for data in ({}, {"pid": 123, "owned": False, "creationTimeTicks": "123"},
                         {"pid": True, "owned": True, "creationTimeTicks": "123"},
                         {"pid": 123, "owned": True, "creationTimeTicks": "not-a-time"}):
                windows.terminate_owned_word(data)
            kernel.assert_not_called()

    def test_cleanup_pins_handle_and_rechecks_creation_time_before_termination(self):
        ticks = 133900000001234567
        def times(handle, created, *unused):
            created._obj.dwLowDateTime = ticks & 0xffffffff
            created._obj.dwHighDateTime = ticks >> 32
            return True
        kernel = SimpleNamespace(OpenProcess=Mock(return_value=99),
                                 GetProcessTimes=Mock(side_effect=times),
                                 TerminateProcess=Mock(return_value=True),
                                 WaitForSingleObject=Mock(), CloseHandle=Mock())
        with patch.object(windows, "_kernel32", return_value=kernel):
            windows.terminate_owned_word({"pid": 123, "owned": True, "creationTimeTicks": str(ticks)})
        kernel.TerminateProcess.assert_called_once_with(99, 1)
        kernel.WaitForSingleObject.assert_called_once_with(99, 3000)
        kernel.CloseHandle.assert_called_once_with(99)
        kernel.TerminateProcess.reset_mock()
        with patch.object(windows, "_kernel32", return_value=kernel):
            windows.terminate_owned_word({"pid": 123, "owned": True, "creationTimeTicks": str(ticks + 1)})
        kernel.TerminateProcess.assert_not_called()
        self.assertEqual(kernel.CloseHandle.call_count, 2)

    def test_pdf_helper_preserves_docx_when_shell_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"unchanged")
            with patch.object(word_pdf.sys, "platform", "win32"), \
                 patch.object(word_pdf, "launch", side_effect=FileNotFoundError("private-student-path")):
                with self.assertRaisesRegex(ValueError, "Helper step: launching-helper") as error:
                    word_pdf.convert(source)
            self.assertNotIn("private-student-path", str(error.exception))
            self.assertEqual(source.read_bytes(), b"unchanged")

    def test_old_pdf_is_never_returned_after_a_failed_new_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"unchanged")
            source.with_suffix(".pdf").write_bytes(b"%PDF-1.4 old\n%%EOF")
            process = SimpleNamespace(returncode=1, wait=Mock(return_value=1))
            with patch.object(word_pdf.sys, "platform", "win32"), \
                 patch.object(word_pdf, "launch", return_value=process):
                with self.assertRaises(ValueError):
                    word_pdf.convert(source)
            self.assertFalse(source.with_suffix(".pdf").exists())
            self.assertEqual(source.read_bytes(), b"unchanged")

    def test_word_open_uses_word_arguments_and_restores_link_preferences(self):
        import engine
        word = SimpleNamespace(Options=SimpleNamespace(UpdateLinksAtOpen=True),
                               Documents=SimpleNamespace(Open=Mock()))
        com = SimpleNamespace(CoInitialize=Mock(), CoUninitialize=Mock())
        client = SimpleNamespace(Dispatch=Mock(return_value=word))
        with patch.object(engine.os, "name", "nt"), \
             patch.object(engine, "Path", return_value=SimpleNamespace(resolve=Mock(return_value="record.docx"))), \
             patch.dict(sys.modules, {"pythoncom": com, "win32com": SimpleNamespace(client=client),
                                      "win32com.client": client}):
            result = engine.handle("open-word", {"filename": "record.docx"})
        self.assertTrue(result["opened"])
        self.assertNotIn("UpdateLinks", word.Documents.Open.call_args.kwargs)
        self.assertTrue(word.Options.UpdateLinksAtOpen)
        com.CoUninitialize.assert_called_once()

    @unittest.skipUnless(sys.platform == "win32", "Requires Windows PowerShell, not installed Word")
    def test_powershell_conversion_contract_with_existing_word_fixture(self):
        # Run the actual script/parser with a fake Word object. No Office or
        # student document is opened; only the COM creation command is replaced.
        fixture = r"""
$global:fixtureClosed = $false
$global:fixtureQuit = $false
$global:fixtureAlerts = 1
$global:fixtureWord = [pscustomobject]@{
    Visible = $true; AutomationSecurity = 1
    Options = [pscustomobject]@{ UpdateLinksAtOpen = $true }
}
function Save-Fixture {
    $value = @{
        closed = $global:fixtureClosed; quit = $global:fixtureQuit
        visible = $global:fixtureWord.Visible
        security = $global:fixtureWord.AutomationSecurity
        links = $global:fixtureWord.Options.UpdateLinksAtOpen
        alerts = $global:fixtureAlerts
    } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($env:RECORDLY_WORD_FIXTURE_RESULT, $value)
}
$global:fixtureWord | Add-Member ScriptProperty DisplayAlerts {
    $global:fixtureAlerts
} {
    param($value)
    $global:fixtureAlerts = $value
    Save-Fixture
}
$windows = [pscustomobject]@{}
$windows | Add-Member ScriptMethod Item { param($index) return [pscustomobject]@{ Hwnd = 0 } }
$global:fixtureDocument = [pscustomobject]@{ Windows = $windows }
$global:fixtureDocument | Add-Member ScriptMethod ExportAsFixedFormat {
    param($target, $format, $openAfter)
    if (($format -ne 17) -or $openAfter) { throw 'Invalid export arguments.' }
    [IO.File]::WriteAllBytes($target, [Text.Encoding]::ASCII.GetBytes("%PDF-1.4 fixture`n%%EOF"))
}
$global:fixtureDocument | Add-Member ScriptMethod Close {
    param($save)
    if ($save -ne 0) { throw 'Must not save the source.' }
    $global:fixtureClosed = $true
}
$documents = [pscustomobject]@{ Count = 0 }
$documents | Add-Member ScriptMethod Open {
    param($file, $confirm, $readOnly, $recent, $p1, $p2, $revert, $p3, $p4, $format, $encoding, $visible)
    if ($confirm -or (-not $readOnly) -or $recent -or $revert -or $visible) {
        throw 'Invalid Word opening arguments.'
    }
    return $global:fixtureDocument
}
$global:fixtureWord | Add-Member NoteProperty Documents $documents
$global:fixtureWord | Add-Member ScriptMethod Quit { $global:fixtureQuit = $true; Save-Fixture }
function New-Object {
    param([string]$ComObject)
    if ($ComObject -ne 'Word.Application') { throw 'Unexpected object creation.' }
    return $global:fixtureWord
}
"""
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "unicode-\u03a9.docx"
            source.write_bytes(b"unchanged DOCX")
            request = source.with_suffix(".word-request.json")
            target = source.with_suffix(".pdf")
            request.write_text(json.dumps({"source": str(source), "target": str(target)}), encoding="utf-8")
            observations = Path(folder) / "observations.json"
            with patch.object(windows, "SCRIPT", fixture + windows.SCRIPT), \
                 patch.dict(os.environ, {"RECORDLY_WORD_FIXTURE_RESULT": str(observations)}):
                process = windows.launch(request)
                try:
                    exit_code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
                    self.fail("The Windows fixture exceeded its bounded execution time.")
            details = json.loads(request.with_suffix(".status.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(exit_code, 0, {k: details.get(k) for k in ("stage", "step", "code", "errorType")})
            self.assertEqual(details["stage"], "pdf-written")
            self.assertFalse(details["owned"])
            self.assertTrue(target.read_bytes().startswith(b"%PDF-"))
            self.assertEqual(source.read_bytes(), b"unchanged DOCX")
            state = json.loads(observations.read_text(encoding="utf-8-sig"))
            self.assertEqual(state, {"closed": True, "quit": False, "visible": True,
                                     "security": 1, "links": True, "alerts": 1})

    @unittest.skipUnless(sys.platform == "win32", "Requires Windows PowerShell, not installed Word")
    def test_actual_powershell_parser_and_process_probe_without_starting_word(self):
        with patch("sys.stdout", new_callable=io.StringIO) as output:
            code = windows.check_automation()
        self.assertEqual(code, 0, "The Windows helper smoke check failed before any Word operation.")
        self.assertEqual(json.loads(output.getvalue()),
                         {"status": "ready", "backend": "powershell-word", "wordStarted": False})


if __name__ == "__main__":
    unittest.main()
