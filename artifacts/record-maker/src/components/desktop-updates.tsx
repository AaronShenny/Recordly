import { useEffect, useState } from "react";
import { useStore, errMsg } from "@/hooks/use-workspace";
import { UPDATE_SUPPORT, updateFailure, type UpdateStatus } from "../../services/update-flow";
import { feature } from "@/lib/workflow-api";

/** Non-modal: even a required-update failure must not lock student work. */
export function DesktopUpdates() {
  const { syncNow, drafts, runtime } = useStore();
  const [status, setStatus] = useState<UpdateStatus | null>(window.recordlyUpdateNotice || null);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState("");
  const invoke = window.__TAURI__?.core.invoke;
  useEffect(() => {
    if (!invoke) return;
    let disposed = false, reading = false;
    const read = async () => {
      if (reading) return;
      reading = true;
      try {
        const next = await invoke<UpdateStatus>("desktop_request", { method: "updates-status", payload: null });
        if (!disposed && next.state !== "idle") setStatus(next);
      } catch { /* A status poll must never interrupt editing. */ }
      finally { reading = false; }
    };
    const timer = window.setInterval(() => { if (!document.hidden) void read(); }, 2000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [invoke]);
  if (!invoke || !status || !["error", "downloaded", "downloading", "retrying", "verifying"].includes(status.state)) return null;
  const key = `${status.state}:${status.version || ""}`;
  if (key === dismissed) return null;
  const act = async (install: boolean) => {
    setBusy(true);
    try {
      if (install) {
        if (drafts.size) throw new Error("Finish the highlighted draft fields before restarting.");
        // Flush both local edits and Drive before the native restart guard.
        if (runtime?.driveConnected) {
          await syncNow();
          await feature("restart-update");
        } else {
          // Native preflight distinguishes a truly fresh installation from
          // cached accounts; cached work still requires the normal Drive guard.
          await invoke("desktop_request", { method: "updates-install-startup", payload: null });
        }
      } else {
        const next = await feature<UpdateStatus>("check-updates");
        setStatus(next);
      }
    } catch (error) { setStatus(updateFailure(errMsg(error))); }
    finally { setBusy(false); }
  };
  return <aside role={status.state === "error" ? "alert" : "status"} data-testid="desktop-update-notice"
    style={{ padding: "10px 20px", borderBottom: "1px solid var(--line, #dedbd1)", background: "var(--paper, #fbfaf5)", display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
    <span style={{ flex: "1 1 300px", fontSize: 13 }}>
      {status.message || "A Recordly update is available."}
      {status.state === "error" && !status.message?.includes(UPDATE_SUPPORT) && <> Support: {UPDATE_SUPPORT}.</>}
      {status.state === "downloading" && status.total ? ` ${Math.min(100, Math.floor((status.downloaded || 0) * 100 / status.total))}%` : ""}
    </span>
    {status.state === "downloaded" && <button className="btn" disabled={busy || !!drafts.size} onClick={() => void act(true)}>Install and restart</button>}
    {status.state === "error" && <button className="btn" disabled={busy} onClick={() => void act(false)}>{busy ? "Retrying…" : "Retry update"}</button>}
    <button className="btn" disabled={busy} onClick={() => setDismissed(key)} aria-label="Dismiss update notice">Dismiss</button>
  </aside>;
}
