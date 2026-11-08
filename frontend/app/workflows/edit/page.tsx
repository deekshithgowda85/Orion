import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, MoreHorizontal, Play, Share2 } from "lucide-react";
import { EditableWorkflow } from "@/components/workflows/EditableWorkflow";

export const metadata: Metadata = { title: "Edit workflow" };

export default function EditWorkflowPage() {
  return (
    <main className="flex min-h-screen flex-col bg-background">
      <header className="workflow-editor-topbar">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href="/workflows"
            className="workflow-editor-icon-button"
            aria-label="Back to workflows"
            title="Back to workflows"
          >
            <ArrowLeft className="size-4" />
          </Link>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">Orion workflow</p>
            <p className="truncate text-[11px] text-muted-foreground">Research pipeline · Draft</p>
          </div>
        </div>
        <div className="hidden items-center gap-1 rounded-lg border border-border bg-surface p-1 sm:flex">
          <span className="rounded-md bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-sm">
            Editor
          </span>
          <span className="px-3 py-1.5 text-xs text-muted-foreground">Executions</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-muted-foreground md:inline">Saved locally</span>
          <button type="button" className="workflow-editor-topbar-button">
            <Share2 className="size-3.5" />
            Share
          </button>
          <button type="button" className="workflow-editor-topbar-button">
            <Play className="size-3.5" />
            Test
          </button>
          <button type="button" className="workflow-editor-icon-button" aria-label="More workflow actions">
            <MoreHorizontal className="size-4" />
          </button>
        </div>
      </header>
      <div className="min-h-0 flex-1">
        <EditableWorkflow />
      </div>
    </main>
  );
}
