import type { DesktopBridge } from "./contracts";
import { makeWorkspace } from "../fixtures";

const unavailable = async (): Promise<never> => {
  throw new Error("Design preview only: native file, clipboard and Python actions are not connected.");
};
export const bridge: DesktopBridge = {
  getRuntime: async () => ({
    mode: "desktop", version: "0.3.0", platform: "Windows design preview",
    storageLabel: "Sample data in preview memory only", driveConnected: true, pythonAvailable: true,
  }),
  loadWorkspace: async () => makeWorkspace(),
  saveWorkspace: async () => ({
    savedAt: new Date().toISOString(), revisionId: "preview-revision",
    pendingItems: 0, storage: "browser",
  }),
  importSource: unavailable, pasteImage: unavailable,
  checkPython: unavailable, inspectSnapshot: unavailable,
};
