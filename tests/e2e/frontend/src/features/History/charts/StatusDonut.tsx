import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { BatchResult } from "@/shared/types";
import { statusCounts } from "./chartData";

export const CHART_HEIGHT_PX = 220;

export function StatusDonut({ batch }: { batch: BatchResult }) {
  const data = statusCounts(batch);
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
      <PieChart>
        <Pie data={data} dataKey="count" nameKey="status" innerRadius={45} outerRadius={80}>
          {data.map((d) => (
            <Cell key={d.status} fill={`var(--cobre-${d.status})`} />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
