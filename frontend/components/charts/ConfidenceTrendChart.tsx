"use client";

import { useMemo } from "react";
import { format } from "date-fns";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { safeParseDate } from "@/lib/format";
import type { HistoryItem } from "@/types/research";

interface Point {
  label: string;
  ticker: string;
  confidence: number;
}

/** Confidence score across the most recent completed runs (oldest → newest). */
export function ConfidenceTrendChart({ items }: { items: HistoryItem[] }) {
  const data = useMemo<Point[]>(() => {
    return items
      .filter((i) => i.status === "completed" && i.confidence_score !== null)
      .map((i) => ({ item: i, date: safeParseDate(i.started_at) }))
      .filter((x): x is { item: HistoryItem; date: Date } => x.date !== null)
      .sort((a, b) => a.date.getTime() - b.date.getTime())
      .slice(-20)
      .map(({ item, date }) => ({
        label: format(date, "MMM d HH:mm"),
        ticker: item.ticker,
        confidence: Number((item.confidence_score ?? 0).toFixed(3)),
      }));
  }, [items]);

  if (data.length < 2) {
    return (
      <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
        Complete a couple of runs to see the confidence trend.
      </div>
    );
  }

  return (
    <div className="h-[200px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <defs>
            <linearGradient id="confFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#533afd" stopOpacity={0.24} />
              <stop offset="100%" stopColor="#533afd" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#e3e8ee" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "#64748d", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            minTickGap={32}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tick={{ fill: "#64748d", fontSize: 10, fontFamily: "var(--font-jetbrains)" }}
            tickLine={false}
            axisLine={false}
          />
          <ReferenceLine y={0.8} stroke="#9b6829" strokeDasharray="4 4" strokeOpacity={0.6} />
          <Tooltip
            cursor={{ stroke: "#533afd", strokeOpacity: 0.4 }}
            contentStyle={{
              background: "#ffffff",
              border: "1px solid #e3e8ee",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#64748d" }}
            formatter={(value, _name, item) => {
              const ticker =
                typeof item === "object" && item !== null && "payload" in item
                  ? (item.payload as Point).ticker
                  : "";
              return [Number(value).toFixed(2), ticker ? `Confidence · ${ticker}` : "Confidence"];
            }}
          />
          <Area
            type="monotone"
            dataKey="confidence"
            stroke="#533afd"
            strokeWidth={2}
            fill="url(#confFill)"
            dot={{ r: 2.5, fill: "#533afd", strokeWidth: 0 }}
            activeDot={{ r: 4 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
