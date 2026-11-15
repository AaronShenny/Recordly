import type { TemplateConfig, Workspace, SourceFile } from "./contracts";
import { previewCloud, setPreviewCloud, previewDocuments } from "../fixtures";

export type ImportRow = { number: number | null; title: string; question: string; sourcePages?: number[]; confidence?: string };
export type ImportResult = { entries?: ImportRow[]; columns?: string[]; rows?: Record<string, string>[]; warnings: string[] };
export type DocumentFile = { id: string; name: string; format: "docx" | "pdf"; subjectId: string; programIds: string[]; createdAt: string; byteLength: number; dataBase64?: string };
export type GenerationResult = { documents: DocumentFile[]; failures: { number?: number; message: string }[]; snapshotAt: string };
export type CloudStatus = { connected: boolean; configured: boolean; account?: { name: string; email: string }; state: string; message?: string; lastSyncAt?: string; pending?: boolean; busy?: boolean; switching?: boolean; revision?: string; syncedRevision?: string };
export type ConflictReview = { token: string; scope: "workspace"; account: string; localSavedAt?: string; remoteSavedAt?: string; localSubjects: number; remoteSubjects: number };

const previewOnly = (): never => { throw new Error("Design preview only. This action needs the installed app; no real file, account or Drive data was changed."); };
export async function feature<T = any>(action: string, _payload: Record<string, unknown> = {}): Promise<T> {
  if (action === "cloud-status") return { ...previewCloud } as T;
  if (action === "sync-drive") return setPreviewCloud({ state: "synced", pending: false, busy: false, lastSyncAt: new Date().toISOString() }) as T;
  if (action === "update-status" || action === "check-updates") return { state: "disabled", message: "Updates are not configured in this design preview." } as T;
  if (action === "list-documents") return [...previewDocuments] as T;
  return previewOnly();
}
export const cloudStatus = () => feature<CloudStatus>("cloud-status");
export const syncDrive = () => feature<CloudStatus>("sync-drive");
export const connectDrive = async (): Promise<CloudStatus> => previewOnly();
export const configureGoogle = connectDrive;
export const logoutCleanup = connectDrive;
export const exportDiagnostics = async (): Promise<{ saved: boolean }> => previewOnly();
export const checkUpdates = () => feature<{ state: string; message?: string }>("check-updates");
export const updateStatus = () => feature<{ state: string; message?: string }>("update-status");
export const restartForUpdate = async () => previewOnly();
export const listDocuments = async (): Promise<DocumentFile[]> => [...previewDocuments];
export const openDocument = async (_doc: DocumentFile, _action: "open" | "download" = "download"): Promise<void> => previewOnly();
export const exportSavedPdf = async (_id: string): Promise<{ documents: DocumentFile[] }> => previewOnly();
export const localSourceFolder = async (): Promise<SourceFile[]> => previewOnly();
export const importQuestions = async (_file: File, _pages = "", _subjectId?: string): Promise<ImportResult> => previewOnly();
export const generateDocuments = async (_workspace: Workspace, _subjectId: string, _programIds: string[], _mode: "individual" | "combined", _pdf: boolean, _token?: string): Promise<GenerationResult> => previewOnly();
export async function base64File(file: File): Promise<string> {
  if (file.size > 20 * 1024 * 1024) throw new Error("Choose a file smaller than 20 MB.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("File could not be read."));
    reader.onload = () => resolve(String(reader.result).split(",")[1]!);
    reader.readAsDataURL(file);
  });
}
export const inspectTemplate = async (_file: File): Promise<{ template: TemplateConfig; warnings: string[] }> => previewOnly();
