import type { AgentLoadRun } from "@/shared/types";
import { fmtCpm, fmtMean, fmtMs, fmtPercent, fmtSeconds } from "../format";

interface Props {
  run: AgentLoadRun;
}

/** Cards de KPI da carga por agente: sessões e provedor, aprovação, vazão e latência. */
export function AgentSummaryCards({ run }: Props) {
  const t = run.totals;
  const requested = run.config.concurrency;
  const started = run.sessions.started;
  const sessionNotes = [...(started < requested ? [`${started} subiram`] : []), run.agent.label];
  const cards: Array<{ accent: string; value: string; label: string }> = [
    {
      accent: started < requested ? "fail" : "mcp",
      value: String(requested),
      label: `Sessões simultâneas (${sessionNotes.join(", ")})`,
    },
    { accent: "", value: String(t.calls), label: `Execuções (${t.ok} completas)` },
    {
      accent: t.calls > 0 && t.pass_rate < 1 ? "partial" : "pass",
      value: t.calls > 0 ? fmtPercent(t.pass_rate) : "—",
      label: "Aprovação",
    },
    {
      accent: t.error_rate > 0 ? "fail" : "pass",
      value: fmtPercent(t.error_rate),
      label: "Taxa de erro",
    },
    { accent: "rate", value: fmtCpm(t.throughput_cpm), label: "Vazão" },
    { accent: "time", value: fmtMs(t.p50_ms), label: "Latência p50" },
    { accent: "time", value: fmtMs(t.p95_ms), label: "Latência p95" },
    { accent: "time", value: fmtMs(t.p99_ms), label: "Latência p99" },
    { accent: "", value: fmtMean(t.tool_calls_mean), label: "Tool-calls médios" },
    { accent: "timeout", value: String(t.timeouts), label: "Timeouts" },
    { accent: "mcp", value: fmtSeconds(run.duration_seconds), label: "Duração da carga" },
  ];

  return (
    <div className="nm-summary" aria-label="Resumo da carga">
      {cards.map((c) => (
        <div key={c.label} className="nm-card" data-accent={c.accent || undefined}>
          <div className="nm-card-value">{c.value}</div>
          <div className="nm-card-label">{c.label}</div>
        </div>
      ))}
    </div>
  );
}
