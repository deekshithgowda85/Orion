"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Citation } from "@/types/research";

interface Row {
  type: string;
  count: number;
}

/** Number of citations per source type. */
export function SourceMixChart({ citations }: { citations: Citation[] }) {
  const data = useMemo<Row[]>(() => {
    const counts = new Map<string, number>();
    citations.forEach((c) => counts.set(c.source_type, (counts.get(c.source_type) ?? 0) + 1));
    return [...counts.entries()]
      .map(([type, count]) => ({ type, count }))
      .sort((a, b) => b.count - a.count);
  }, [citations]);

  if (data.length === 0) return null;

  return (
    <div className="h-[160px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
          <CartesianGrid stroke="#e3e8ee" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="type"
            tick={{ fill: "#64748d", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fill: "#64748d", fontSize: 10, fontFamily: "var(--font-jetbrains)" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgb(83 58 253 / 0.08)" }}
            contentStyle={{
              background: "#ffffff",
              border: "1px solid #e3e8ee",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#64748d" }}
          />
          <Bar dataKey="count" name="Citations" fill="#533afd" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
