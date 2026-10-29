import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Customized,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/shared/charts/ChartCard";
import { SvgLegend } from "@/shared/charts/SvgLegend";
import type { LoadSeriesPoint } from "@/shared/types";
import { AXIS_TICK, AXIS_LINE, GRID_STROKE, TOOLTIP, LINE_CURSOR } from "@/shared/charts/axis";

interface Props {
  series: LoadSeriesPoint[];
  /** Altura menor para o gráfico ao vivo dentro do progresso. */
  compact?: boolean;
  /** Prefixo do nome dos PNGs baixados (o load_id); sem ele vale "carga". */
  fileStem?: string;
  /** Janela da carga, para descartar o bucket final quase vazio (ver ``trimPartialTail``). */
  durationSeconds?: number;
  /** Título e rótulos do gráfico de vazão; o padrão é o das chamadas por segundo (tools). */
  throughput?: { title: string; ok: string; failed: string };
}

const DEFAULT_THROUGHPUT = {
  title: "Vazão no tempo (chamadas/s)",
  ok: "ok",
  failed: "erros e timeouts",
};

const LATENCY_LEGEND = [
  { label: "p50", color: "var(--nm-chart-p50)" },
  { label: "p95", color: "var(--nm-chart-p95)" },
];

const HEIGHT_PX = 240;
const COMPACT_HEIGHT_PX = 160;
// Abaixo disto o último bucket abrange pouco da janela e só traz o rabo das chamadas em voo.
const MIN_TAIL_COVERAGE_S = 0.5;

/**
 * Descarta o último bucket quando a janela só o abrange por menos de MIN_TAIL_COVERAGE_S:
 * ele conta poucas chamadas e pareceria uma queda de vazão e um salto de latência que
 * não existiram.
 */
export function trimPartialTail(
  series: LoadSeriesPoint[],
  durationSeconds: number,
): LoadSeriesPoint[] {
  const last = series[series.length - 1];
  if (!last || series.length < 2) return series;
  return durationSeconds - last.t < MIN_TAIL_COVERAGE_S ? series.slice(0, -1) : series;
}

/** Latência (p50/p95 de cada segundo) e vazão ao longo da carga. */
export function LoadCharts({
  series,
  compact = false,
  fileStem = "carga",
  durationSeconds,
  throughput = DEFAULT_THROUGHPUT,
}: Props) {
  const height = compact ? COMPACT_HEIGHT_PX : HEIGHT_PX;
  const data = useMemo(
    () =>
      (durationSeconds === undefined ? series : trimPartialTail(series, durationSeconds)).map(
        (p) => ({
          t: p.t,
          p50_ms: p.p50_ms,
          p95_ms: p.p95_ms,
          ok_calls: Math.max(p.calls - p.failed, 0),
          failed: p.failed,
        }),
      ),
    [series, durationSeconds],
  );

  if (data.length === 0) {
    return <div className="nm-no-data">Sem série temporal para esta carga</div>;
  }

  return (
    <div className="nm-charts" data-compact={compact}>
      <ChartCard title="Latência no tempo (ms)" fileName={`${fileStem}-latencia.png`}>
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 28, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
            <XAxis stroke={AXIS_LINE} dataKey="t" tick={AXIS_TICK} unit=" s" />
            <YAxis stroke={AXIS_LINE} tick={AXIS_TICK} width={48} />
            <Tooltip {...TOOLTIP} cursor={LINE_CURSOR} />
            <Customized component={<SvgLegend items={LATENCY_LEGEND} />} />
            <Line
              type="monotone"
              dataKey="p50_ms"
              name="p50"
              stroke="var(--nm-chart-p50)"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="p95_ms"
              name="p95"
              stroke="var(--nm-chart-p95)"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title={throughput.title} fileName={`${fileStem}-vazao.png`}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 28, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
            <XAxis stroke={AXIS_LINE} dataKey="t" tick={AXIS_TICK} unit=" s" />
            <YAxis stroke={AXIS_LINE} tick={AXIS_TICK} width={48} allowDecimals={false} />
            <Tooltip {...TOOLTIP} />
            <Customized
              component={
                <SvgLegend
                  items={[
                    { label: throughput.ok, color: "var(--nm-chart-throughput)" },
                    { label: throughput.failed, color: "var(--nm-chart-failed)" },
                  ]}
                />
              }
            />
            <Bar
              dataKey="ok_calls"
              name={throughput.ok}
              stackId="calls"
              fill="var(--nm-chart-throughput)"
              isAnimationActive={false}
            />
            <Bar
              dataKey="failed"
              name={throughput.failed}
              stackId="calls"
              fill="var(--nm-chart-failed)"
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
    </div>
  );
}
