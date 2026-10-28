import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { toolUsage } from "./chartData";
import { AXIS_TICK, AXIS_LINE, TOOLTIP } from "@/shared/charts/axis";

const HEIGHT_PX = 320;
/** Altura dos rótulos inclinados do eixo X: os nomes das tools são longos. */
const LABEL_HEIGHT_PX = 110;
const MAX_BAR_PX = 48;

export function ToolUsage({ batch }: { batch: BatchResult }) {
  const data = toolUsage(batch);
  return (
    <ResponsiveContainer width="100%" height={HEIGHT_PX}>
      <BarChart data={data} margin={{ top: 8, left: 32, right: 16 }}>
        <XAxis
          stroke={AXIS_LINE}
          dataKey="tool"
          interval={0}
          angle={-45}
          textAnchor="end"
          height={LABEL_HEIGHT_PX}
          tick={AXIS_TICK}
        />
        <YAxis stroke={AXIS_LINE} allowDecimals={false} tick={AXIS_TICK} />
        <Tooltip {...TOOLTIP} />
        <Bar dataKey="calls" name="Chamadas" fill="var(--nm-primary)" maxBarSize={MAX_BAR_PX} />
      </BarChart>
    </ResponsiveContainer>
  );
}
