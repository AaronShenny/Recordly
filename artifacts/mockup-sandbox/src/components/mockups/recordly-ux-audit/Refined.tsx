import "./_group.css";
import "./_refined/_app.css";
import { WorkspaceProvider } from "./_shared/hooks/use-workspace";
import { useHashRoute } from "./_refined/components/kit";
import Dashboard from "./_refined/pages/dashboard";
import SubjectPage from "./_refined/pages/subject";
import Editor from "./_refined/pages/editor";
import Documents from "./_refined/pages/documents";
import Settings from "./_refined/pages/settings";
import Trash from "./_refined/pages/trash";
import Template from "./_refined/pages/template";
import Import from "./_refined/pages/import";

function RefinedRoutes() {
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
export function Refined() {
  return <WorkspaceProvider><RefinedRoutes /><div className="audit-preview-note" role="note">DESIGN PREVIEW · Fictional data · Edits stay in memory · No Drive, native file actions or document bytes · Reload resets</div></WorkspaceProvider>;
}
