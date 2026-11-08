import type { Metadata } from "next";
import Link from "next/link";
import { Pencil } from "lucide-react";
import { PageHeader } from "@/components/layout/PageHeader";
import { SchedulesSection } from "@/components/workflows/SchedulesSection";
import { WorkflowCanvas } from "@/components/workflows/WorkflowCanvas";

export const metadata: Metadata = { title: "Workflows" };

export default function WorkflowsPage() {
  return (
    <>
      <PageHeader
        title="Workflows"
        description="The multi-agent DAG behind every run, plus your recurring schedules."
        actions={
          <Link
            href="/workflows/edit"
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Pencil className="size-4" />
            Edit workflow
          </Link>
        }
      />
      <div className="space-y-6">
        <WorkflowCanvas />
        <SchedulesSection />
      </div>
    </>
  );
}
