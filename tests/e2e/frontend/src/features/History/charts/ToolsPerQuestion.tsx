import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { BatchResult } from "@/shared/types";
import { toolsPerQuestion } from "./chartData";
import { CHART_HEIGHT_PX } from "./StatusDonut";

export function ToolsPerQuestion({ batch }: { batch: BatchResult }) {
  return (
    <ResponsiveContainer width="100%" height={CHART_HEIGHT_PX}>
      <BarChart data={toolsPerQuestion(batch)} margin={{ top: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--cobre-border)" />
        <XAxis dataKey="bucket" tick={{ fontSize: 10 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
        <Tooltip />
        <Bar dataKey="count" name="Perguntas" fill="var(--cobre-primary)" />
      </BarChart>
    </ResponsiveContainer>
  );
}
