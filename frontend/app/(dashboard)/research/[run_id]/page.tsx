import type { Metadata } from "next";
import { LiveRunView } from "@/components/research/LiveRunView";

interface RunPageProps {
  params: Promise<{ run_id: string }>;
}

export async function generateMetadata({ params }: RunPageProps): Promise<Metadata> {
  const { run_id } = await params;
  return { title: `Run ${run_id.slice(0, 8)}` };
}

export default async function RunPage({ params }: RunPageProps) {
  const { run_id } = await params;
  return <LiveRunView runId={run_id} />;
}
