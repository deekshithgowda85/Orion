import { OrgGate } from "@/components/auth/OrgGate";

export default function WorkflowEditorLayout({ children }: { children: React.ReactNode }) {
  return (
    <OrgGate>
      <div className="workflow-editor-app min-h-screen">{children}</div>
    </OrgGate>
  );
}
