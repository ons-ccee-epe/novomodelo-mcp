import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { BatchResult } from "@/shared/types";
import { statusColor, statusCounts } from "./chartData";

export const CHART_HEIGHT_PX = 220;

export function StatusDonut({ batch }: { batch: BatchResult }) {
  const data = statusCounts(batch);
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
      <PieChart>
        <Pie data={data} dataKey="count" nameKey="status" innerRadius={45}
          outerRadius={75}
          label={(p: { name?: string; value?: number }) => `${p.name}: ${p.value}`}
        >
          {data.map((d) => (
            <Cell key={d.status} fill={statusColor(d.status)} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
    </ResponsiveContainer>
  );
}
