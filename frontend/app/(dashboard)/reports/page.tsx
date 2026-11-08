import type { Metadata } from "next";
import { PageHeader } from "@/components/layout/PageHeader";
import { ReportsTable } from "@/components/reports/ReportsTable";

export const metadata: Metadata = { title: "Reports" };

export default function ReportsPage() {
  return (
    <>
      <PageHeader
        title="Reports"
        description="Search, filter and download every research report in your organization."
      />
      <ReportsTable />
    </>
  );
}
