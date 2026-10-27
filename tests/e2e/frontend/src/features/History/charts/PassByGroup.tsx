import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { decimal } from "../format";
import { passByGroup } from "./chartData";
import { CHART_HEIGHT_PX } from "./StatusDonut";
import { AXIS_TICK, AXIS_LINE, GRID_STROKE, TOOLTIP } from "@/shared/charts/axis";

const MAX_PERCENT = 100;

export function PassByGroup({ batch }: { batch: BatchResult }) {
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
      <BarChart data={passByGroup(batch)} margin={{ top: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
        <XAxis stroke={AXIS_LINE} dataKey="group" tick={AXIS_TICK} />
        <YAxis stroke={AXIS_LINE} domain={[0, MAX_PERCENT]} unit="%" tick={AXIS_TICK} width={44} />
        <Tooltip {...TOOLTIP} formatter={(v) => `${decimal(Number(v))}%`} />
        <Bar dataKey="pct" name="Aprovação" fill="var(--cobre-pass)" />
      </BarChart>
    </ResponsiveContainer>
  );
}
