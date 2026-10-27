import {
  Bar,
  BarChart,
  CartesianGrid,
  Customized,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartCard } from "@/shared/charts/ChartCard";
import { SvgLegend } from "@/shared/charts/SvgLegend";
import { isAgentRun, type AgentLoadRun, type LoadRun } from "@/shared/types";
import { AXIS_TICK, AXIS_LINE, GRID_STROKE, TOOLTIP } from "@/shared/charts/axis";

const HEIGHT_PX = 280;
const LEGEND = [
  { label: "p95 (ms)", color: "var(--cobre-chart-p95)" },
  { label: "erros e timeouts", color: "var(--cobre-chart-failed)" },
];

export interface PerToolRow {
  name: string;
  p95_ms: number | null;
  failed: number;
}

function statsByName(run: LoadRun | AgentLoadRun) {
  return isAgentRun(run) ? run.per_case : run.per_tool;
}

export function perToolRows(run: LoadRun | AgentLoadRun): PerToolRow[] {
  return Object.entries(statsByName(run)).map(([name, s]) => ({
    name,
    p95_ms: s.p95_ms,
    failed: s.errors + s.timeouts,
  }));
}

/** p95 e erros (com timeouts) por tool, ou por caso nas cargas por agente. */
export function LoadPerToolChart({ run }: { run: LoadRun | AgentLoadRun }) {
  const agent = isAgentRun(run);
  const rows = perToolRows(run);
  const hasCalls = Object.values(statsByName(run)).some((s) => s.calls > 0);

  return (
    <ChartCard
      title={agent ? "p95 e erros por caso" : "p95 e erros por tool"}
      fileName={`${run.load_id}-${agent ? "por-caso" : "por-tool"}.png`}
    >
      {hasCalls ? (
        <ResponsiveContainer width="100%" height={HEIGHT_PX}>
          <BarChart data={rows} margin={{ top: 28, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
            <XAxis stroke={AXIS_LINE} dataKey="name" tick={AXIS_TICK} interval={0} />
            <YAxis stroke={AXIS_LINE} yAxisId="ms" tick={AXIS_TICK} width={48} unit=" ms" />
            <YAxis
              stroke={AXIS_LINE}
              yAxisId="err"
              orientation="right"
              tick={AXIS_TICK}
              width={36}
              allowDecimals={false}
            />
            <Tooltip {...TOOLTIP} />
            <Customized component={<SvgLegend items={LEGEND} />} />
            <Bar
              yAxisId="ms"
              dataKey="p95_ms"
              name="p95 (ms)"
              fill="var(--cobre-chart-p95)"
              isAnimationActive={false}
            />
            <Bar
              yAxisId="err"
              dataKey="failed"
              name="erros e timeouts"
              fill="var(--cobre-chart-failed)"
              isAnimationActive={false}
            />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="cobre-no-data">Sem chamadas</div>
      )}
    </ChartCard>
  );
}
