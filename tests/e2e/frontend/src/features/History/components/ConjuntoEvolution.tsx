import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { passRate } from "@/shared/comparison";
import { conjuntoOf } from "@/shared/conjunto";
import type { BatchResult } from "@/shared/types";
import { formatDate } from "../format";
import {
  AXIS_TICK,
  AXIS_LINE,
  GRID_STROKE,
  TOOLTIP,
  LINE_CURSOR,
} from "@/shared/charts/axis";

const CHART_HEIGHT_PX = 200;
const MAX_PERCENT = 100;

interface Props {
  batch: BatchResult;
  all: BatchResult[];
  baselines: Record<string, string>;
}

export function ConjuntoEvolution({ batch, all, baselines }: Props) {
  const conjunto = conjuntoOf(batch);
  const data = useMemo(
    () =>
      all
        .filter((b) => conjuntoOf(b) === conjunto)
        .sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
        .map((b) => ({
          id: b.batch_id,
          label: formatDate(b.timestamp),
          rate: passRate(b),
        })),
    [all, conjunto],
  );
  const baseline = data.find((d) => d.id === baselines[conjunto]);
  if (data.length < 2) return null;

  return (
    <section className="cobre-panel" aria-label="Evolução do conjunto">
      <h3 className="cobre-section-title">Evolução do conjunto</h3>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
        <LineChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis stroke={AXIS_LINE} dataKey="label" tick={AXIS_TICK} />
          <YAxis
            stroke={AXIS_LINE}
            tick={AXIS_TICK}
            width={44}
            domain={[0, MAX_PERCENT]}
            unit="%"
          />
          <Tooltip
            {...TOOLTIP}
            cursor={LINE_CURSOR}
            formatter={(v) => `${Number(v).toFixed(1)}%`}
          />
          <Line
            type="linear"
            dataKey="rate"
            name="Aprovação"
            stroke="var(--cobre-primary)"
            strokeWidth={2}
            dot={{ r: 3, fill: "var(--cobre-primary)" }}
          />
          {baseline && baseline.rate !== null && (
            <ReferenceDot
              x={baseline.label}
              y={baseline.rate}
              r={7}
              fill="var(--cobre-partial)"
              stroke="var(--cobre-text)"
              label={{ value: "baseline", fontSize: 10, position: "top" }}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}
