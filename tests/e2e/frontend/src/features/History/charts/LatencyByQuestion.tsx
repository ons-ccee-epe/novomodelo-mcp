import { Bar, BarChart, Cell, Customized, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { latencyLegend, latencyRows, statusColor, TOOL_TIME_COLOR } from "./chartData";
import { SvgLegend } from "./SvgLegend";

const ROW_HEIGHT_PX = 22;
const MIN_HEIGHT_PX = 220;
const AXIS_PADDING_PX = 60;
const LABEL_WIDTH_PX = 110;

export function LatencyByQuestion({ batch }: { batch: BatchResult }) {
  const data = latencyRows(batch);
  const height = Math.max(MIN_HEIGHT_PX, data.length * ROW_HEIGHT_PX + AXIS_PADDING_PX);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 44, left: 8, right: 16 }}>
        <XAxis type="number" tick={{ fontSize: 10 }} unit=" ms" />
        <YAxis
          type="category"
          dataKey="test_id"
          width={LABEL_WIDTH_PX}
          interval={0}
          tick={{ fontSize: 10 }}
        />
        <Tooltip />
        <Customized component={<SvgLegend items={latencyLegend(batch)} />} />
        <Bar dataKey="total_ms" name="Total">
          {data.map((r) => (
            <Cell key={r.test_id} fill={statusColor(r.status)} />
          ))}
        </Bar>
        <Bar dataKey="tool_ms" name="Tempo na tool" fill={TOOL_TIME_COLOR} />
      </BarChart>
    </ResponsiveContainer>
  );
}
