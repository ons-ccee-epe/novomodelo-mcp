import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { toolsPerQuestion } from "./chartData";
import { CHART_HEIGHT_PX } from "./StatusDonut";
import { AXIS_TICK, AXIS_LINE, GRID_STROKE, TOOLTIP } from "@/shared/charts/axis";

export function ToolsPerQuestion({ batch }: { batch: BatchResult }) {
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
      <BarChart data={toolsPerQuestion(batch)} margin={{ top: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
        <XAxis stroke={AXIS_LINE} dataKey="bucket" tick={AXIS_TICK} />
        <YAxis stroke={AXIS_LINE} allowDecimals={false} tick={AXIS_TICK} />
        <Tooltip {...TOOLTIP} />
        <Bar dataKey="count" name="Perguntas" fill="var(--nm-primary)" />
      </BarChart>
    </ResponsiveContainer>
  );
}
