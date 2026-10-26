import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { toolUsage } from "./chartData";

const ROW_HEIGHT_PX = 24;
const MIN_HEIGHT_PX = 220;
const AXIS_PADDING_PX = 40;
const LABEL_WIDTH_PX = 130;

export function ToolUsage({ batch }: { batch: BatchResult }) {
  const data = toolUsage(batch);
  const height = Math.max(MIN_HEIGHT_PX, data.length * ROW_HEIGHT_PX + AXIS_PADDING_PX);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <XAxis type="number" allowDecimals={false} tick={{ fontSize: 10 }} />
        <YAxis
          type="category"
          dataKey="tool"
          width={LABEL_WIDTH_PX}
          interval={0}
          tick={{ fontSize: 10 }}
        />
        <Tooltip />
        <Bar dataKey="calls" name="Chamadas" fill="var(--cobre-primary)" />
      </BarChart>
    </ResponsiveContainer>
  );
}
