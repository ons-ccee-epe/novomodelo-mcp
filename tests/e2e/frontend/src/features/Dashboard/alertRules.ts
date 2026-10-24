import type { BatchResult, MetricsHistoryRecord } from "@/shared/types";

/** Limiares em % de variação relativa; espelham as regras do ResultStore. */
export const MCP_DROP_WARNING_PCT = 5;
export const MCP_DROP_CRITICAL_PCT = 10;
export const CORRECT_TOOL_DROP_PCT = 5;
export const LATENCY_INCREASE_PCT = 20;
export const LATENCY_WINDOW = 5;

export type AlertLevel = "warning" | "critical";

export interface Alert {
  level: AlertLevel;
  message: string;
}

function relativeDropPct(reference: number, current: number): number {
  return ((reference - current) / reference) * 100;
}

function orZero(v: number | undefined): number {
  return typeof v === "number" ? v : 0;
}

/**
 * Bateria imediatamente anterior à atual no histórico. Se a atual não está no
 * histórico, não há "anterior" confiável — usar o último registro compararia
 * com uma bateria possivelmente mais nova.
 */
export function previousRecord(
  history: MetricsHistoryRecord[],
  batchId: string,
): MetricsHistoryRecord | null {
  const idx = history.findIndex((h) => h.batch_id === batchId);
  return idx > 0 ? history[idx - 1] : null;
}

function mcpUsageAlert(batch: BatchResult, previous: MetricsHistoryRecord | null): Alert | null {
  if (!previous || previous.pct_mcp_used <= 0) return null;
  const drop = relativeDropPct(previous.pct_mcp_used, orZero(batch.metrics?.pct_mcp_used));
  const text = `MCP usage caiu ${drop.toFixed(1)}% vs anterior`;
  if (drop > MCP_DROP_CRITICAL_PCT) return { level: "critical", message: `⚠️ CRÍTICO: ${text}` };
  if (drop > MCP_DROP_WARNING_PCT) return { level: "warning", message: `⚡ AVISO: ${text}` };
  return null;
}

function correctToolAlert(batch: BatchResult, baseline: BatchResult | null): Alert | null {
  const reference = baseline?.metrics?.pct_correct_tool ?? 0;
  if (reference <= 0) return null;
  const drop = relativeDropPct(reference, orZero(batch.metrics?.pct_correct_tool));
  if (drop <= CORRECT_TOOL_DROP_PCT) return null;
  return { level: "warning", message: `📉 Correct tool caiu ${drop.toFixed(1)}% vs baseline` };
}

function latencyAlert(batch: BatchResult, history: MetricsHistoryRecord[]): Alert | null {
  const current = orZero(batch.metrics?.avg_latency_ms);
  const idx = history.findIndex((h) => h.batch_id === batch.batch_id);
  const before = idx >= 0 ? history.slice(0, idx) : history;
  const window = before.slice(-LATENCY_WINDOW).filter((h) => h.avg_latency_ms > 0);
  if (window.length === 0 || current <= 0) return null;
  const avg = window.reduce((s, h) => s + h.avg_latency_ms, 0) / window.length;
  const increase = ((current - avg) / avg) * 100;
  if (increase <= LATENCY_INCREASE_PCT) return null;
  return {
    level: "warning",
    message: `🐢 Performance: latência aumentou ${increase.toFixed(1)}% (${current.toFixed(0)}ms vs média ${avg.toFixed(0)}ms)`,
  };
}

/** Alertas de saúde da bateria: uso do MCP, acerto de tool e latência. */
export function computeAlerts(
  batch: BatchResult,
  history: MetricsHistoryRecord[],
  baseline: BatchResult | null,
): Alert[] {
  return [
    mcpUsageAlert(batch, previousRecord(history, batch.batch_id)),
    correctToolAlert(batch, baseline),
    latencyAlert(batch, history),
  ].filter((a): a is Alert => a !== null);
}
