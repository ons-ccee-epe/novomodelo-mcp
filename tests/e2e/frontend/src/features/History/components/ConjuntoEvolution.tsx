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
        .map((b) => ({ id: b.batch_id, label: formatDate(b.timestamp), rate: passRate(b) })),
    [all, conjunto],
  );
  const baseline = data.find((d) => d.id === baselines[conjunto]);

  return (
    <section className="cobre-section" aria-label="Evolução do conjunto">
      <h3 className="cobre-section-title">Evolução do conjunto</h3>
      {data.length < 2 ? (
        <p className="cobre-muted">Só há uma bateria deste conjunto.</p>
      ) : (
        <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--cobre-border)" />
            <XAxis dataKey="label" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} width={44} domain={[0, MAX_PERCENT]} unit="%" />
            <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
            <Line
              type="monotone"
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
      )}
    </section>
  );
}
