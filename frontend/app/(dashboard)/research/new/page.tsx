import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/PageHeader";
import { NewResearchForm } from "@/components/research/NewResearchForm";

export const metadata: Metadata = { title: "New Research" };

export default function NewResearchPage() {
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="New research"
        description="Configure a workflow and watch the agents work in real time."
      />
      <NewResearchForm />
    </div>
  );
}
