import type { LoadRun } from "@/shared/types";
import { fmtMs, fmtPercent, fmtRate, fmtSeconds } from "../format";

interface Props {
  run: LoadRun;
}

/** Cards de KPI da carga: sessões simultâneas, vazão, taxa de erro e percentis de latência. */
export function LoadSummaryCards({ run }: Props) {
  const t = run.totals;
  const requested = run.config.concurrency;
  const started = run.startup.started;
  const cards: Array<{ accent: string; value: string; label: string }> = [
    {
      accent: started < requested ? "fail" : "mcp",
      value: String(requested),
      label:
        started < requested ? `Sessões simultâneas (${started} subiram)` : "Sessões simultâneas",
    },
    { accent: "rate", value: fmtRate(t.throughput_cps), label: "Vazão" },
    {
      accent: t.error_rate > 0 ? "fail" : "pass",
      value: fmtPercent(t.error_rate),
      label: "Taxa de erro",
    },
    { accent: "time", value: fmtMs(t.p50_ms), label: "Latência p50" },
    { accent: "time", value: fmtMs(t.p95_ms), label: "Latência p95" },
    { accent: "time", value: fmtMs(t.p99_ms), label: "Latência p99" },
    { accent: "", value: String(t.calls), label: `Chamadas (${t.ok} ok)` },
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
