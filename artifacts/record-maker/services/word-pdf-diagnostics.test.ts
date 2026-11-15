import assert from "node:assert/strict";
import test from "node:test";
import { diagnosticError } from "./diagnostic-policy";

test("Word diagnostics retain fixed helper classifications without private messages", () => {
  const result = diagnosticError(new Error(
    "Microsoft Word PDF export failed during starting-word (Office code: unavailable). " +
    "Helper step: loading-automation. Failure type: ModuleNotFoundError. " +
    "Missing component: pythoncom. Helper exit: 1. C:\\Users\\private-student\\record.docx",
  ));
  assert.deepEqual(result, {
    category: "word-or-pdf", officeStage: "starting-word",
    officeStep: "loading-automation", officeFailureType: "ModuleNotFoundError",
    officeDependency: "pythoncom", officeHelperExit: 1,
  });
  assert.doesNotMatch(JSON.stringify(result), /private-student|record\.docx/);
});

test("Word diagnostics preserve COM codes and reject arbitrary classification text", () => {
  assert.deepEqual(diagnosticError(new Error(
    "Microsoft Word PDF export failed during starting-word (Office code: 0x80040154). " +
    "Helper step: creating-word-instance. Failure type: com_error. Helper exit: 1.",
  )), {
    category: "word-or-pdf", officeCode: "0x80040154", officeStage: "starting-word",
    officeStep: "creating-word-instance", officeFailureType: "com_error", officeHelperExit: 1,
  });
  const unsafe = diagnosticError(new Error(
    "Microsoft Word PDF export failed. Helper step: private-path. " +
    "Failure type: student-name. Missing component: private-module.",
  ));
  assert.deepEqual(unsafe, { category: "word-or-pdf" });
});

test("Windows automation diagnostics retain the backend and safe ownership failure", () => {
  assert.deepEqual(diagnosticError(new Error(
    "Microsoft Word PDF export failed during starting-word (Office code: 0x80131509). " +
    "Helper step: checking-word-process. Automation backend: powershell-word. " +
    "Failure type: WordOwnershipUncertain. Helper exit: 1. private-student-path",
  )), {
    category: "word-or-pdf", officeCode: "0x80131509", officeStage: "starting-word",
    officeStep: "checking-word-process", officeFailureType: "WordOwnershipUncertain",
    officeBackend: "powershell-word", officeHelperExit: 1,
  });
});
