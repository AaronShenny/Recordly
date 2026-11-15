import { beforeRecordScreens, type UpdateRequest, type UpdateStatus } from "../../services/update-flow";

declare global {
  interface Window { recordlyUpdateNotice?: UpdateStatus }
}

/** A small startup view, loaded before React, the workspace, Node or Python. */
export async function startupUpdateScreen(root: HTMLElement): Promise<boolean> {
  const invoke = window.__TAURI__?.core.invoke;
  if (!invoke) return false; // The security bridge itself reports a missing host.
  const request: UpdateRequest = (method, payload = null) => invoke("desktop_request", { method, payload });
  const card = document.createElement("section");
  card.className = "panel panel-pad";
  card.style.cssText = "max-width:540px;margin:16vh auto;padding:32px";
  card.setAttribute("role", "status");
  card.setAttribute("aria-live", "polite");
  const heading = document.createElement("h1");
  heading.style.fontSize = "28px";
  const message = document.createElement("p");
  const progress = document.createElement("progress");
  progress.style.cssText = "width:100%;height:8px";
  const detail = document.createElement("p");
  detail.className = "hint";
  card.append(heading, message, progress, detail);
  root.replaceChildren(card);
  const show = (status: UpdateStatus) => {
    heading.textContent = ["checking", "current", "disabled", "available"].includes(status.state) ? "Opening Recordly…" : "Updating Recordly";
    message.textContent = status.message || "Preparing your update…";
    progress.hidden = ["error", "current", "disabled"].includes(status.state);
    if (status.total && status.total > 0) {
      progress.max = status.total;
      progress.value = Math.min(status.downloaded || 0, status.total);
    } else progress.removeAttribute("value");
    detail.textContent = status.state === "installing" ? "Record screens open after the verified update installs. Your records stay on this computer and in Drive."
      : status.attempt ? `Attempt ${status.attempt} of ${status.maxAttempts || 3}. If updating keeps failing, you can continue working.`
      : "Your saved work will not be removed.";
  };
  let polling = false;
  const timer = window.setInterval(() => {
    if (polling) return;
    polling = true;
    void request("updates-status").then(show).catch(() => undefined).finally(() => { polling = false; });
  }, 400);
  try {
    const result = await beforeRecordScreens(request, show);
    show(result);
    if (result.state === "error") window.recordlyUpdateNotice = result;
    return result.state === "installing";
  } finally { window.clearInterval(timer); }
}
