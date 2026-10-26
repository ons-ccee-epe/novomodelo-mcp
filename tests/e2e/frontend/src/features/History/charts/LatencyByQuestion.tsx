import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { latencyRows } from "./chartData";

const ROW_HEIGHT_PX = 22;
const MIN_HEIGHT_PX = 220;
const AXIS_PADDING_PX = 60;
const LABEL_WIDTH_PX = 110;

export function LatencyByQuestion({ batch }: { batch: BatchResult }) {
  const data = latencyRows(batch);
  const height = Math.max(MIN_HEIGHT_PX, data.length * ROW_HEIGHT_PX + AXIS_PADDING_PX);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <XAxis type="number" tick={{ fontSize: 10 }} unit=" ms" />
        <YAxis
          type="category"
          dataKey="test_id"
          width={LABEL_WIDTH_PX}
          interval={0}
          tick={{ fontSize: 10 }}
        />
        <Tooltip />
        <Legend />
        <Bar dataKey="total_ms" name="Total" fill="var(--cobre-primary)" />
        <Bar dataKey="tool_ms" name="Tool" fill="var(--cobre-partial)" />
      </BarChart>
    </ResponsiveContainer>
  );
}
