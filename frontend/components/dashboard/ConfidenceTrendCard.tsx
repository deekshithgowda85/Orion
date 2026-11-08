"use client";

import { ConfidenceTrendChart } from "@/components/charts/ConfidenceTrendChart";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useResearchHistory } from "@/hooks/useResearchHistory";

export function ConfidenceTrendCard() {
  const { data, isLoading } = useResearchHistory(
    { page: 1, page_size: 50 },
    { refetchIntervalMs: 10_000 },
  );

  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle>Confidence trend</CardTitle>
        <CardDescription>Last 20 completed runs · dashed line = 0.80 threshold</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[200px] w-full" />
        ) : (
          <ConfidenceTrendChart items={data?.items ?? []} />
        )}
      </CardContent>
    </Card>
  );
}
