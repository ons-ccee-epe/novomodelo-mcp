import {
  Bar,
  BarChart,
  Cell,
  Customized,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { BatchResult } from "@/shared/types";
import { latencyLegend, latencyRows, statusColor, TOOL_TIME_COLOR } from "./chartData";
import { SvgLegend } from "@/shared/charts/SvgLegend";
import { AXIS_TICK, AXIS_LINE, TOOLTIP, tooltipNumber } from "@/shared/charts/axis";

const HEIGHT_PX = 400;
/** Altura dos rótulos inclinados do eixo X: os ids das perguntas são longos. */
const LABEL_HEIGHT_PX = 140;
const MAX_BAR_PX = 32;

export function LatencyByQuestion({ batch }: { batch: BatchResult }) {
  const data = latencyRows(batch);
  const legend = latencyLegend(batch);
  return (
    <ResponsiveContainer width="100%" height={HEIGHT_PX}>
      {/* barGap -100%: o tempo na tool (parte do total) fica sobreposto à coluna do total. */}
      <BarChart data={data} barGap="-100%" margin={{ top: 28, left: 48, right: 16 }}>
        <XAxis
          stroke={AXIS_LINE}
          dataKey="test_id"
          interval={0}
          angle={-45}
          textAnchor="end"
          height={LABEL_HEIGHT_PX}
          tick={AXIS_TICK}
        />
        <YAxis stroke={AXIS_LINE} tick={AXIS_TICK} unit=" ms" width={70} />
        <Tooltip {...TOOLTIP} formatter={(v) => `${tooltipNumber(Math.round(Number(v)))} ms`} />
        <Customized component={<SvgLegend items={legend} perRow={legend.length} />} />
        <Bar dataKey="total_ms" name="Total" maxBarSize={MAX_BAR_PX}>
          {data.map((r) => (
            <Cell key={r.test_id} fill={statusColor(r.status)} />
          ))}
        </Bar>
        <Bar
          dataKey="tool_ms"
          name="Tempo na tool"
          fill={TOOL_TIME_COLOR}
          maxBarSize={MAX_BAR_PX}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
