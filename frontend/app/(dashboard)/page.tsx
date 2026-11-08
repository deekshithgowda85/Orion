import type { Metadata } from "next";
import { ConfidenceTrendCard } from "@/components/dashboard/ConfidenceTrendCard";
import { OverviewStats } from "@/components/dashboard/OverviewStats";
import { QuickSubmit } from "@/components/dashboard/QuickSubmit";
import { RecentRunsTable } from "@/components/dashboard/RecentRunsTable";
import { PageHeader } from "@/components/layout/PageHeader";

export const metadata: Metadata = { title: "Overview" };

export default function OverviewPage() {
  return (
    <>
      <PageHeader
        title="Overview"
        description="Live status of your autonomous research workflows."
      />
      <div className="space-y-6">
        <OverviewStats />
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <QuickSubmit />
          </div>
          <div className="lg:col-span-2">
            <ConfidenceTrendCard />
          </div>
        </div>
        <RecentRunsTable />
      </div>
    </>
  );
}
