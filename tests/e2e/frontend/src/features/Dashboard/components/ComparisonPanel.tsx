import { useMemo } from "react";
import type { BatchResult } from "@/shared/types";

interface Props {
  current: BatchResult;
  previous: BatchResult;
}

const MAX_LISTED_TESTS = 10;

function Delta({ value, invert = false, suffix }: { value: number; invert?: boolean; suffix: string }) {
  const improvement = invert ? value < 0 : value > 0;
  const degradation = invert ? value > 0 : value < 0;
  const trend = improvement ? "better" : degradation ? "worse" : "flat";
  const arrow = improvement ? "↑" : degradation ? "↓" : "→";
  const display = value === 0 ? "0" : `${value > 0 ? "+" : "-"}${Math.abs(value).toFixed(1)}`;
  return (
    <span className="cobre-delta" data-trend={trend}>
      {arrow} {display}
      {suffix}
    </span>
  );
}

/** Comparacao entre a bateria atual e outra selecionada. */
export function ComparisonPanel({ current, previous }: Props) {
  const diff = useMemo(() => {
    const cur = new Map((current.test_results ?? []).map((t) => [t.test_id, t.status]));
    const prev = new Map((previous.test_results ?? []).map((t) => [t.test_id, t.status]));
    const regressions: string[] = [];
    const improvements: string[] = [];
    const newTests: string[] = [];
    const removed: string[] = [];
    for (const [id, status] of cur) {
      if (!prev.has(id)) newTests.push(id);
      else if (prev.get(id) === "pass" && status !== "pass") regressions.push(id);
      else if (prev.get(id) !== "pass" && status === "pass") improvements.push(id);
    }
    for (const id of prev.keys()) if (!cur.has(id)) removed.push(id);
    return { regressions, improvements, newTests, removed };
  }, [current, previous]);

  const cm = current.metrics ?? ({} as BatchResult["metrics"]);
  const pm = previous.metrics ?? ({} as BatchResult["metrics"]);
  const nz = (v: number | undefined) => (typeof v === "number" ? v : 0);
  const dMcp = nz(cm.pct_mcp_used) - nz(pm.pct_mcp_used);
  const dTool = nz(cm.pct_correct_tool) - nz(pm.pct_correct_tool);
  const dResult = nz(cm.pct_correct_result) - nz(pm.pct_correct_result);
  const dLatency = nz(cm.avg_latency_ms) - nz(pm.avg_latency_ms);

  function block(title: string, items: string[], kind: "critical" | "healthy" | "warning") {
    if (items.length === 0) return null;
    return (
      <div className="cobre-banner cobre-banner-stacked" data-kind={kind}>
        <strong>
          {title} ({items.length})
        </strong>
        <div className="cobre-banner-list">
          {items.slice(0, MAX_LISTED_TESTS).map((t) => (
            <div key={t}>• {t}</div>
          ))}
          {items.length > MAX_LISTED_TESTS && (
            <em>… +{items.length - MAX_LISTED_TESTS} itens</em>
          )}
        </div>
      </div>
    );
  }

  return (
    <section className="cobre-section">
      <h2 className="cobre-section-title">
        Comparação: {current.batch_id} vs {previous.batch_id}
      </h2>
      <div className="cobre-metrics-grid">
        <div className="cobre-metrics-card">
          <h4>Δ MCP Used</h4>
          <Delta value={dMcp} suffix="%" />
        </div>
        <div className="cobre-metrics-card">
          <h4>Δ Correct Tool</h4>
          <Delta value={dTool} suffix="%" />
        </div>
        <div className="cobre-metrics-card">
          <h4>Δ Correct Result</h4>
          <Delta value={dResult} suffix="%" />
        </div>
        <div className="cobre-metrics-card">
          <h4>Δ Latency</h4>
          <Delta value={dLatency} invert suffix="ms" />
        </div>
      </div>
      {block("⚠️ Regressões", diff.regressions, "critical")}
      {block("✓ Melhorias", diff.improvements, "healthy")}
      {block("➕ Novos testes", diff.newTests, "warning")}
      {block("➖ Testes removidos", diff.removed, "warning")}
    </section>
  );
}
