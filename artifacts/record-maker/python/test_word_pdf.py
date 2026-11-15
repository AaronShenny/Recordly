import json
from pathlib import Path
import subprocess
import tempfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import word_pdf

class WordPdfTests(unittest.TestCase):
    def test_missing_automation_dependency_is_reported_before_word_starts(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"original DOCX")
            request = source.with_suffix(".word-request.json")
            request.write_text(json.dumps({"source": str(source), "target": str(source.with_suffix(".pdf"))}))
            with patch.dict(sys.modules, {"pythoncom": None}):
                self.assertEqual(word_pdf.run_helper(request), 1)
            details = json.loads(request.with_suffix(".status.json").read_text())
            self.assertEqual(details["stage"], "starting-word")
            self.assertEqual(details["step"], "loading-automation")
            self.assertEqual(details["errorType"], "ModuleNotFoundError")
            self.assertEqual(details["dependency"], "pythoncom")
            self.assertNotIn(str(source), json.dumps(details))
            self.assertEqual(source.read_bytes(), b"original DOCX")

    def test_com_initialization_failure_is_recorded_without_unbalanced_cleanup(self):
        pythoncom = SimpleNamespace(CoInitialize=Mock(side_effect=RuntimeError("private-student-path")),
                                    CoUninitialize=Mock())
        modules = {"pythoncom": pythoncom,
                   "win32com": SimpleNamespace(),
                   "win32com.client": SimpleNamespace(dynamic=SimpleNamespace()),
                   "win32process": SimpleNamespace(), "win32api": SimpleNamespace()}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"original DOCX")
            request = source.with_suffix(".word-request.json")
            request.write_text(json.dumps({"source": str(source), "target": str(source.with_suffix(".pdf"))}))
            with patch.dict(sys.modules, modules):
                self.assertEqual(word_pdf.run_helper(request), 1)
            details = json.loads(request.with_suffix(".status.json").read_text())
            self.assertEqual(details["step"], "initializing-com")
            self.assertEqual(details["errorType"], "RuntimeError")
            self.assertNotIn("private-student-path", json.dumps(details))
            pythoncom.CoUninitialize.assert_not_called()

    def test_non_com_word_configuration_error_keeps_its_safe_failure_type(self):
        class Word:
            Hwnd = 1
            Quit = Mock()
            def __setattr__(self, name, value):
                raise AttributeError("private-student-path")
        word = Word()
        pythoncom = SimpleNamespace(
            CoInitialize=Mock(), CoUninitialize=Mock(), CLSIDFromProgID=Mock(return_value="word"),
            CoCreateInstance=Mock(return_value=object()), CLSCTX_LOCAL_SERVER=4, IID_IDispatch=object())
        modules = {"pythoncom": pythoncom, "win32com": SimpleNamespace(),
                   "win32com.client": SimpleNamespace(dynamic=SimpleNamespace(Dispatch=Mock(return_value=word))),
                   "win32process": SimpleNamespace(GetWindowThreadProcessId=Mock(return_value=(1, 100))),
                   "win32api": SimpleNamespace(OpenProcess=Mock(side_effect=PermissionError("private-student-path")))}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"original DOCX")
            request = source.with_suffix(".word-request.json")
            request.write_text(json.dumps({"source": str(source), "target": str(source.with_suffix(".pdf"))}))
            with patch.dict(sys.modules, modules):
                self.assertEqual(word_pdf.run_helper(request), 1)
            details = json.loads(request.with_suffix(".status.json").read_text())
            self.assertEqual(details["step"], "configuring-word")
            self.assertEqual(details["errorType"], "AttributeError")
            self.assertFalse(details["owned"])
            self.assertNotIn("private-student-path", json.dumps(details))
            pythoncom.CoUninitialize.assert_called_once()
            word.Quit.assert_not_called()

    def test_hresult_can_be_recovered_from_exception_arguments(self):
        details = word_pdf._error_details(RuntimeError(-2147221164, "private-student-path"))
        self.assertEqual(details["code"], "0x80040154")
        self.assertNotIn("private-student-path", json.dumps(details))

    def test_child_exit_without_status_does_not_blame_office(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"original DOCX")
            process = SimpleNamespace(returncode=-1073741515, wait=Mock(return_value=-1073741515))
            with patch.object(word_pdf.sys, "platform", "win32"), patch.object(word_pdf.subprocess, "Popen", return_value=process):
                with self.assertRaises(ValueError) as raised:
                    word_pdf.convert(source)
            message = str(raised.exception)
            self.assertIn("Helper step: launching-helper.", message)
            self.assertIn("Helper exit: -1073741515.", message)
            self.assertIn("does not establish an Office installation problem", message)
            self.assertNotIn("repair Microsoft Office", message)
            self.assertEqual(source.read_bytes(), b"original DOCX")

    def test_successful_conversion_does_not_change_docx(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"original DOCX")
            class Process:
                returncode = 0
                def wait(self, timeout=None):
                    source.with_suffix(".pdf").write_bytes(b"%PDF-1.4 fixture\n%%EOF")
                    source.with_suffix(".word-request.status.json").write_text(json.dumps({"stage": "pdf-written"}))
                    return 0
            with patch.object(word_pdf.sys, "platform", "win32"), patch.object(word_pdf.subprocess, "Popen", return_value=Process()):
                self.assertEqual(word_pdf.convert(source), b"%PDF-1.4 fixture\n%%EOF")
            self.assertEqual(source.read_bytes(), b"original DOCX")

    def test_word_timeout_is_bounded_and_never_kills_unowned_word(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"original DOCX")
            source.with_suffix(".word-request.status.json").write_text(json.dumps({
                "stage": "opening-document", "pid": 123, "owned": False,
            }))
            class Process:
                killed = False
                def wait(self, timeout=None):
                    if timeout is not None and not self.killed:
                        self.timeout = timeout
                        source.with_suffix(".word-request.status.json").write_text(json.dumps({
                            "stage": "opening-document", "pid": 123, "owned": False,
                        }))
                        raise subprocess.TimeoutExpired("fixture", timeout)
                    return 0
                def kill(self):
                    self.killed = True
            process = Process()
            with patch.object(word_pdf.sys, "platform", "win32"), patch.object(word_pdf.subprocess, "Popen", return_value=process), patch.object(word_pdf.subprocess, "run") as kill_word:
                with self.assertRaisesRegex(ValueError, "timed out after 30 seconds.*opening-document"):
                    word_pdf.convert(source)
                self.assertEqual(process.timeout, 30)
                self.assertTrue(process.killed)
                kill_word.assert_not_called()
            self.assertEqual(source.read_bytes(), b"original DOCX")

    def test_office_failure_exposes_safe_stage_and_code_not_private_exception(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "record.docx"
            source.write_bytes(b"original DOCX")
            source.with_suffix(".word-request.status.json").write_text(json.dumps({
                "stage": "starting-word", "failed": True, "code": "0x80080005",
            }))
            class Process:
                def wait(self, timeout=None):
                    source.with_suffix(".word-request.status.json").write_text(json.dumps({
                        "stage": "starting-word", "failed": True, "code": "0x80080005",
                    }))
                    return 1
            with patch.object(word_pdf.sys, "platform", "win32"), patch.object(word_pdf.subprocess, "Popen", return_value=Process()):
                with self.assertRaisesRegex(ValueError, "starting-word.*0x80080005"):
                    word_pdf.convert(source)

if __name__ == "__main__":
    unittest.main()
