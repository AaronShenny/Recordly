/** Pure startup coordinator: also exercised without a Windows desktop. */
export const UPDATE_SUPPORT = "extapano@gmail.com";
export type UpdateStatus = {
  state: string; priority?: string; version?: string; message?: string;
  attempt?: number; maxAttempts?: number; downloaded?: number; total?: number;
};
export type UpdateRequest = <T = UpdateStatus>(method: string, payload?: unknown) => Promise<T>;
export function updateFailure(message = "Recordly could not install the update."): UpdateStatus {
  return { state: "error", message: `${message} You can continue working. If this keeps happening, contact ${UPDATE_SUPPORT}.` };
}

export async function beforeRecordScreens(
  request: UpdateRequest,
  show: (status: UpdateStatus) => void,
  wait: (ms: number) => Promise<void> = ms => new Promise(resolve => setTimeout(resolve, ms)),
): Promise<UpdateStatus> {
  let status: UpdateStatus = { state: "checking", message: "Checking GitHub Releases…" };
  show(status);
  for (let attempt = 1; attempt <= 3; attempt++) {
    try { status = await request("updates-startup"); }
    catch { status = updateFailure("The update service is unavailable."); }
    show(status);
    if (status.state !== "error" || status.priority !== "high" || attempt === 3) break;
    show({ ...status, state: "retrying", attempt, maxAttempts: 3, message: "The required update is unavailable. Trying again…" });
    await wait(attempt * 500);
  }
  if (status.priority !== "high" || !["available", "downloaded"].includes(status.state)) return status;
  try {
    if (status.state === "available") {
      show({ ...status, state: "downloading", message: "Downloading the required update from GitHub Releases…" });
      // Native download includes three bounded attempts, live progress and both
      // signature checks. Failed downloads explicitly allow ordinary editing.
      status = await request("updates-download");
    }
    if (status.state !== "downloaded") return status;
    status = { ...status, state: "installing", message: "Checking saved work before installing the update…" };
    show(status);
    // Local onboarding/instance ownership must complete before any installer
    // can start. It does not mount the record editor or open browser storage.
    await request("boot");
    await request("updates-install-startup");
    return { ...status, message: "The verified update is installing. Recordly will restart…" };
  } catch {
    return updateFailure("Installation could not finish safely. Your saved work was preserved.");
  }
}
