import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { TOOLTIP } from "@/shared/charts/axis";
import type { BatchResult } from "@/shared/types";
import { STATUS_LABEL, statusColor, statusCounts } from "./chartData";

export const CHART_HEIGHT_PX = 220;

export function StatusDonut({ batch }: { batch: BatchResult }) {
  const data = statusCounts(batch).map((s) => ({
    ...s,
    label: STATUS_LABEL[s.status],
  }));
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="label"
          innerRadius={45}
          outerRadius={75}
          stroke="var(--cobre-surface)"
          strokeWidth={2}
          label={(p: { name?: string; value?: number }) =>
            `${p.name}: ${p.value}`
          }
        >
          {data.map((d) => (
            <Cell key={d.status} fill={statusColor(d.status)} />
          ))}
        </Pie>
        <Tooltip {...TOOLTIP} />
      </PieChart>
    </ResponsiveContainer>
  );
}
