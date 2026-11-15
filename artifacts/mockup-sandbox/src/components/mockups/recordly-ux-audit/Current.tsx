import "./_group.css";
import "./_current/_app.css";
import { WorkspaceProvider } from "./_shared/hooks/use-workspace";
import { useHashRoute } from "./_current/components/kit";
import Dashboard from "./_current/pages/dashboard";
import SubjectPage from "./_current/pages/subject";
import Editor from "./_current/pages/editor";
import Documents from "./_current/pages/documents";
import Settings from "./_current/pages/settings";
import Trash from "./_current/pages/trash";
import Template from "./_current/pages/template";
import Import from "./_current/pages/import";

function CurrentRoutes() {
  const [a, b, c] = useHashRoute();
  if (a === "subject" && b) return <SubjectPage id={b} />;
  if (a === "program" && b && c) return <Editor sid={b} pid={c} />;
  if (a === "documents") return <Documents sid={b} />;
  if (a === "settings") return <Settings />;
  if (a === "trash") return <Trash />;
  if (a === "template" && b) return <Template sid={b} />;
  if (a === "import" && b) return <Import sid={b} />;
  return <Dashboard />;
}
export function Current() {
  return <WorkspaceProvider><CurrentRoutes /><div className="audit-preview-note" role="note">CURRENT · Extracted app UI · Fictional sample data · No Drive connection · Reload to reset</div></WorkspaceProvider>;
}
