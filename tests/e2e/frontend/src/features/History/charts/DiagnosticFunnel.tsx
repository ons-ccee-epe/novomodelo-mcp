import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { decimal } from "../format";
import { funnel } from "./chartData";
import { CHART_HEIGHT_PX } from "./StatusDonut";

const MAX_PERCENT = 100;
const LABEL_WIDTH_PX = 110;

export function DiagnosticFunnel({ batch }: { batch: BatchResult }) {
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
      <BarChart data={funnel(batch)} layout="vertical" margin={{ left: 8, right: 16 }}>
        <XAxis type="number" domain={[0, MAX_PERCENT]} unit="%" tick={{ fontSize: 10 }} />
        <YAxis
          type="category"
          dataKey="step"
          width={LABEL_WIDTH_PX}
          interval={0}
          tick={{ fontSize: 10 }}
        />
        <Tooltip formatter={(v) => `${decimal(Number(v))}%`} />
        <Bar dataKey="pct" name="Percentual" fill="var(--cobre-primary)" />
      </BarChart>
    </ResponsiveContainer>
  );
}
