import {createContext,useCallback,useContext,useState,type ReactNode} from 'react';
import type {Program,RuntimeInfo,Subject,Workspace} from '../lib/contracts';
import type {CloudStatus,GenerationResult,ConflictReview} from '../lib/workflow-api';
import {mergeGenerationChoice,type GenerationChoice} from '../lib/generation-choice';
import {makeWorkspace,previewCloud,setPreviewCloud,previewDocuments,PREVIEW_TIME} from '../fixtures';
export type {GenerationChoice} from '../lib/generation-choice';
export {programChecks,requiredMappings} from '../lib/program-checks';
export type SaveKind = "idle" | "dirty" | "saving" | "saved" | "error" | "invalid";
export type SaveState = { kind: SaveKind; message?: string; savedAt?: string; storage?: string; pending?: number };
export type Toast = { id: number; text: string; tone: "info" | "error" };

type Store = {
  workspace: Workspace | null;
  workspaceRevision: string | null;
  loadError: string | null;
  reload: () => void;
  update: (fn: (w: Workspace) => Workspace) => void;
  save: SaveState;
  saveNow: () => void;
  syncNow: () => Promise<void>;
  reviewConflict: () => Promise<ConflictReview>;
  resolveConflict: (token: string, choice: "local" | "drive") => Promise<void>;
  closing: { state: "idle" | "saving" | "error"; message?: string };
  retryClose: () => void;
  cancelClose: () => void;
  runtime: RuntimeInfo | null;
  runtimeError: string | null;
  toasts: Toast[];
  notify: (text: string, tone?: "info" | "error") => void;
  dismiss: (id: number) => void;
  drafts: Set<string>;
  setDraft: (key: string, on: boolean) => void;
  cloud: CloudStatus | null;
  cloudError: string | null;
  refreshCloud: () => Promise<CloudStatus | null>;
  isClean: boolean;
  gen: GenJob;
  startGeneration: (subjectId: string, programIds: string[], mode: "individual" | "combined", pdf: boolean) => void;
  docsVersion: number;
  generationChoices: Record<string, GenerationChoice>;
  setGenerationChoice: (subjectId: string, choice: Partial<GenerationChoice>) => void;
};
export type GenJob = { state: "idle" | "running" | "done" | "error"; subjectId?: string; count?: number; mode?: string; startedAt?: string; result?: GenerationResult; error?: string };
export function cloudLabel(c: CloudStatus | null): { tone: "good" | "warn" | "alert" | "neutral"; text: string } {
  if (!c) return { tone: "neutral", text: "Checking Drive…" };
  if (!c.connected) return { tone: "neutral", text: c.configured ? "Drive not signed in" : "Drive not connected" };
  if (c.state === "conflict") return { tone: "alert", text: "Drive conflict · review in Settings" };
  if (c.state === "error") return { tone: "alert", text: "Drive sync error" };
  if (c.state === "syncing" || c.busy) return { tone: "warn", text: "Syncing to Drive…" };
  if (c.pending) return { tone: "warn", text: "Changes waiting to sync" };
  if (c.state === "synced" && !c.pending) return { tone: "good", text: "Saved to Drive" };
  return { tone: "warn", text: "Connected · not yet synced" };
}


const Ctx=createContext<Store|null>(null);
export const errMsg=(e:unknown)=>e instanceof Error?e.message:String(e);
export const nowIso=()=>new Date().toISOString();
export const newId=()=>crypto.randomUUID();
export function WorkspaceProvider({children}:{children:ReactNode}){
 const [workspace,setWorkspace]=useState<Workspace>(makeWorkspace);
 const [save,setSave]=useState<SaveState>({kind:'idle'});
 const [cloud,setCloud]=useState<CloudStatus>(previewCloud);
 const [drafts,setDrafts]=useState(new Set<string>());
 const [toasts,setToasts]=useState<Toast[]>([]);
 const [gen,setGen]=useState<GenJob>({state:'idle'});
 const [docsVersion,setDocsVersion]=useState(0);
 const [generationChoices,setChoices]=useState<Record<string,GenerationChoice>>({});
 const setDraft=useCallback((key:string,on:boolean)=>setDrafts(previous=>{
   if(previous.has(key)===on)return previous;
   const next=new Set(previous);
   if(on)next.add(key);else next.delete(key);
   return next;
 }),[]);
 const notify=useCallback((text:string,tone:'info'|'error'='info')=>{const id=Date.now()+Math.random();setToasts(t=>[...t.slice(-2),{id,text,tone}]);window.setTimeout(()=>setToasts(t=>t.filter(x=>x.id!==id)),4500);},[]);
 const syncNow=async()=>{setSave({kind:'saved',savedAt:nowIso(),storage:'preview memory'});setCloud(setPreviewCloud({state:'synced',pending:false,busy:false}));notify('Preview only: simulated local save and Drive sync. No real files were changed.');};
 const value:Store={workspace,workspaceRevision:'preview-revision',loadError:null,reload:()=>setWorkspace(makeWorkspace()),
 update:fn=>{setWorkspace(w=>fn(w));setSave({kind:'saved',savedAt:nowIso(),storage:'preview memory'});},save,saveNow:()=>{void syncNow();},syncNow,
 runtime:{mode:'desktop',version:'0.3.0',platform:'Windows design preview',storageLabel:'Sample workspace — memory only',driveConnected:true,pythonAvailable:true},runtimeError:null,
 toasts,notify,dismiss:id=>setToasts(t=>t.filter(x=>x.id!==id)),drafts,setDraft,cloud,cloudError:null,
 refreshCloud:async()=>{setCloud({...previewCloud});return previewCloud;},isClean:!drafts.size,closing:{state:'idle'},retryClose:()=>notify('Preview only: no window will close.'),cancelClose:()=>{},
 reviewConflict:async()=>({token:'preview',scope:'workspace',account:'student@example.edu',localSubjects:3,remoteSubjects:3}),resolveConflict:async()=>notify('Preview only: no local or Drive data was overwritten.'),
 gen,docsVersion,generationChoices,setGenerationChoice:(id,choice)=>setChoices(v=>({...v,[id]:mergeGenerationChoice(v[id],choice)})),
 startGeneration:(subjectId,programIds,mode,pdf)=>{if(!programIds.length)return;setGen({state:'running',subjectId,count:programIds.length,mode,startedAt:nowIso()});const snapshotAt=nowIso();window.setTimeout(()=>{setGen({state:'done',subjectId,count:programIds.length,mode,result:{snapshotAt,documents:previewDocuments.filter(d=>d.subjectId===subjectId&&(pdf||d.format==='docx')),failures:[]}});setDocsVersion(v=>v+1);notify('Design preview: showing sample generation results. No DOCX or PDF was created.');},900);},
 };return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export function useStore() {
  const s = useContext(Ctx);
  if (!s) throw new Error("WorkspaceProvider missing");
  return s;
}

/* Pure helpers */
export const activeSubjects = (w: Workspace) => w.subjects.filter(s => !s.trashedAt);
export const activePrograms = (s: Subject) => s.programs.filter(p => !p.trashedAt).sort((a, b) => a.number - b.number);
export const pad = (n: number) => String(n).padStart(2, "0");
export const slug = (s: string) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "untitled";
export const nextNumber = (s: Subject) => { const used = new Set(activePrograms(s).map(p => p.number)); let n = 1; while (used.has(n)) n++; return n; };
export const initials = (name: string) => name.split(/\s+/).filter(w => /^[A-Za-z]/.test(w) && !/^(of|and|the|lab)$/i.test(w)).slice(0, 2).map(w => w[0]!.toUpperCase()).join("") || "S";

export { programState } from "../lib/program-checks";
export function blankProgram(number: number, title = "", question = ""): Program {
  const t = nowIso();
  return { id: newId(), number, title: title.slice(0, 500), question: question.slice(0, 100000), createdAt: t, updatedAt: t, trashedAt: null, sources: [], outputs: [], outputMayBeStale: false };
}

export function mapSubject(w: Workspace, id: string, fn: (s: Subject) => Subject): Workspace {
  return { ...w, subjects: w.subjects.map(s => (s.id === id ? fn(s) : s)) };
}
export function mapProgram(w: Workspace, sid: string, pid: string, fn: (p: Program) => Program, markStale = false): Workspace {
  const t = nowIso();
  return mapSubject(w, sid, s => ({ ...s, updatedAt: t, programs: s.programs.map(p => {
    if (p.id !== pid) return p;
    const n = fn(p);
    return { ...n, updatedAt: t, outputMayBeStale: markStale && n.outputs.length > 0 ? true : n.outputMayBeStale };
  }) }));
}
