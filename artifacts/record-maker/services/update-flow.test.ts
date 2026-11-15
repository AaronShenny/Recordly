import { test } from "node:test";
import assert from "node:assert/strict";
import { beforeRecordScreens, UPDATE_SUPPORT, type UpdateRequest, type UpdateStatus } from "./update-flow";

function host(responses: Record<string, UpdateStatus | Error | (() => UpdateStatus)>) {
  const calls: string[] = [];
  const request: UpdateRequest = async <T>(method: string) => {
    calls.push(method);
    const value = responses[method];
    if (value instanceof Error) throw value;
    return (typeof value === "function" ? value() : value) as T;
  };
  return { calls, request };
}
const noWait = async () => {};
test("normal releases open screens without downloading, booting services or installing", async () => {
  const h = host({ "updates-startup": { state: "available", priority: "normal" } });
  assert.equal((await beforeRecordScreens(h.request, () => {}, noWait)).state, "available");
  assert.deepEqual(h.calls, ["updates-startup"]);
});
test("high-priority releases download and finish native safety preflight before installation", async () => {
  const h = host({ "updates-startup": { state: "available", priority: "high" },
    "updates-download": { state: "downloaded", priority: "high" },
    boot: { state: "ready" }, "updates-install-startup": { state: "installed" } });
  assert.equal((await beforeRecordScreens(h.request, () => {}, noWait)).state, "installing");
  assert.deepEqual(h.calls, ["updates-startup", "updates-download", "boot", "updates-install-startup"]);
});
test("unavailable required metadata retries three times then lets normal work proceed", async () => {
  const h = host({ "updates-startup": { state: "error", priority: "high", message: `Contact ${UPDATE_SUPPORT}. You can continue working.` } });
  const shown: UpdateStatus[] = [];
  const result = await beforeRecordScreens(h.request, s => shown.push(s), noWait);
  assert.equal(result.state, "error");
  assert.equal(h.calls.length, 3);
  assert.equal(shown.filter(s => s.state === "retrying").length, 2);
  assert.match(result.message!, /continue working/);
  assert.match(result.message!, /extapano@gmail\.com/);
});
test("ordinary offline startup is bounded and never interpreted as a required update", async () => {
  const h = host({ "updates-startup": new Error("offline") });
  const result = await beforeRecordScreens(h.request, () => {}, noWait);
  assert.equal(result.state, "error");
  assert.equal(h.calls.length, 1);
  assert.match(result.message!, /continue working/);
});
test("failed download or verification never reaches boot or installer and does not lock editing", async () => {
  const h = host({ "updates-startup": { state: "available", priority: "high" },
    "updates-download": { state: "error", message: `Contact ${UPDATE_SUPPORT}. You can continue working.` } });
  assert.equal((await beforeRecordScreens(h.request, () => {}, noWait)).state, "error");
  assert.deepEqual(h.calls, ["updates-startup", "updates-download"]);
});
test("failed Drive/preflight or installer preserves work, reports support and opens ordinary app", async () => {
  for (const failure of ["boot", "updates-install-startup"]) {
    const h = host({ "updates-startup": { state: "downloaded", priority: "high" },
      boot: { state: "ready" }, "updates-install-startup": { state: "installed" }, [failure]: new Error("Drive did not acknowledge work") });
    const result = await beforeRecordScreens(h.request, () => {}, noWait);
    assert.equal(result.state, "error");
    assert.match(result.message!, /preserved/);
    assert.match(result.message!, /extapano@gmail\.com/);
    if (failure === "boot") assert.ok(!h.calls.includes("updates-install-startup"));
  }
});
test("disabled/current update feeds never prevent offline work", async () => {
  for (const state of ["disabled", "current"]) {
    const h = host({ "updates-startup": { state } });
    assert.equal((await beforeRecordScreens(h.request, () => {}, noWait)).state, state);
    assert.equal(h.calls.length, 1);
  }
});
