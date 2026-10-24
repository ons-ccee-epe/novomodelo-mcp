import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { LoadSeriesPoint } from "@/shared/types";

interface Props {
  series: LoadSeriesPoint[];
  /** Altura menor para o gráfico ao vivo dentro do progresso. */
  compact?: boolean;
  /** Janela da carga, para descartar o bucket final quase vazio (ver ``trimPartialTail``). */
  durationSeconds?: number;
}

const HEIGHT_PX = 240;
const COMPACT_HEIGHT_PX = 160;
// Abaixo disto o último bucket cobre pouco da janela e só traz o rabo das chamadas em voo.
const MIN_TAIL_COVERAGE_S = 0.5;

/**
 * Descarta o último bucket quando a janela só o cobre por menos de MIN_TAIL_COVERAGE_S:
 * ele conta poucas chamadas e pareceria uma queda de vazão e um salto de latência que
 * não existiram.
 */
export function trimPartialTail(series: LoadSeriesPoint[], durationSeconds: number): LoadSeriesPoint[] {
  const last = series[series.length - 1];
  if (!last || series.length < 2) return series;
  return durationSeconds - last.t < MIN_TAIL_COVERAGE_S ? series.slice(0, -1) : series;
}

/** Latência (p50/p95 de cada segundo) e vazão ao longo da carga. */
export function LoadCharts({ series, compact = false, durationSeconds }: Props) {
  const height = compact ? COMPACT_HEIGHT_PX : HEIGHT_PX;
  const data = useMemo(
    () =>
      (durationSeconds === undefined ? series : trimPartialTail(series, durationSeconds)).map((p) => ({
        t: p.t,
        p50_ms: p.p50_ms,
        p95_ms: p.p95_ms,
        ok_calls: Math.max(p.calls - p.failed, 0),
        failed: p.failed,
      })),
    [series, durationSeconds],
  );

  if (data.length === 0) {
    return <div className="cobre-no-data">Sem série temporal para esta carga</div>;
  }

  return (
    <div className="cobre-charts" data-compact={compact}>
      <div className="cobre-chart">
        <div className="cobre-chart-title">Latência no tempo (ms)</div>
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--cobre-border)" />
            <XAxis dataKey="t" tick={{ fontSize: 10 }} unit=" s" />
            <YAxis tick={{ fontSize: 10 }} width={48} />
            <Tooltip />
            <Legend />
            <Line
              type="monotone"
              dataKey="p50_ms"
              name="p50"
              stroke="var(--cobre-chart-p50)"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="p95_ms"
              name="p95"
              stroke="var(--cobre-chart-p95)"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="cobre-chart">
        <div className="cobre-chart-title">Vazão no tempo (chamadas/s)</div>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--cobre-border)" />
            <XAxis dataKey="t" tick={{ fontSize: 10 }} unit=" s" />
            <YAxis tick={{ fontSize: 10 }} width={48} allowDecimals={false} />
            <Tooltip />
            <Legend />
            <Bar
              dataKey="ok_calls"
              name="ok"
              stackId="calls"
              fill="var(--cobre-chart-throughput)"
              isAnimationActive={false}
            />
            <Bar
              dataKey="failed"
              name="erros e timeouts"
              stackId="calls"
              fill="var(--cobre-chart-failed)"
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
