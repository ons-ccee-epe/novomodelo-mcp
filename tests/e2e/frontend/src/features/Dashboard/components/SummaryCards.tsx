import type { BatchResult } from "@/shared/types";

interface Props {
  batch: BatchResult;
}

/** Cards de KPI do sumario da bateria. */
export function SummaryCards({ batch }: Props) {
  const m = batch.metrics ?? ({} as BatchResult["metrics"]);
  const num = (v: number | undefined) => (typeof v === "number" ? v : 0);
  const cards: Array<{ accent: string; value: string; label: string }> = [
    { accent: "", value: String(batch.total_tests ?? 0), label: "Total" },
    { accent: "pass", value: String(batch.passed ?? 0), label: "Passed" },
    { accent: "fail", value: String(batch.failed ?? 0), label: "Failed" },
    { accent: "timeout", value: String(batch.timeout ?? 0), label: "Timeout" },
    { accent: "mcp", value: `${num(m.pct_mcp_used).toFixed(1)}%`, label: "MCP Used" },
    { accent: "rate", value: `${num(m.pct_correct_tool).toFixed(1)}%`, label: "Correct Tool" },
    { accent: "time", value: `${num(m.avg_latency_ms).toFixed(0)}ms`, label: "Avg Latency" },
  ];

  return (
    <div className="cobre-summary">
      {cards.map((c) => (
        <div key={c.label} className="cobre-card" data-accent={c.accent || undefined}>
          <div className="cobre-card-value">{c.value}</div>
          <div className="cobre-card-label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
