import type { BatchResult, TestStatus } from "@/shared/types";

const STATUS_ORDER: TestStatus[] = ["pass", "partial", "fail", "timeout", "skip"];
const BUCKETS = ["0", "1", "2", "3+"] as const;
const MAX_EXACT_BUCKET = 3;

export type ToolBucket = (typeof BUCKETS)[number];

export function statusCounts(b: BatchResult): Array<{ status: TestStatus; count: number }> {
  return STATUS_ORDER.map((status) => ({
    status,
    count: b.test_results.filter((r) => r.status === status).length,
  })).filter((s) => s.count > 0);
}

export function latencyRows(
  b: BatchResult,
): Array<{ test_id: string; total_ms: number; tool_ms: number; status: TestStatus }> {
  return b.test_results
    .map((r) => ({
      test_id: r.test_id,
      total_ms: r.latency_ms,
      tool_ms: r.tool_latency_ms ?? 0,
      status: r.status,
    }))
    .sort((a, c) => c.total_ms - a.total_ms);
}

export function toolUsage(b: BatchResult): Array<{ tool: string; calls: number }> {
  const counts = new Map<string, number>();
  for (const r of b.test_results) {
    for (const call of r.all_tool_calls ?? []) {
      counts.set(call.name, (counts.get(call.name) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([tool, calls]) => ({ tool, calls }))
    .sort((a, c) => c.calls - a.calls);
}

export function toolsPerQuestion(b: BatchResult): Array<{ bucket: ToolBucket; count: number }> {
  const counts = new Map<ToolBucket, number>(BUCKETS.map((k) => [k, 0]));
  for (const r of b.test_results) {
    const n = r.all_tool_calls?.length ?? 0;
    const bucket: ToolBucket = n >= MAX_EXACT_BUCKET ? "3+" : (String(n) as ToolBucket);
    counts.set(bucket, (counts.get(bucket) ?? 0) + 1);
  }
  return BUCKETS.map((bucket) => ({ bucket, count: counts.get(bucket) ?? 0 }));
}

export function passByGroup(b: BatchResult): Array<{ group: string; pct: number }> {
  return Object.entries(b.metrics_by_group ?? {}).map(([group, m]) => ({ group, pct: m.pct_pass }));
}

export function funnel(
  b: BatchResult,
): Array<{ step: "Usou o MCP" | "Tool certa" | "Resultado certo"; pct: number }> {
  const m = b.metrics;
  return [
    { step: "Usou o MCP", pct: m?.pct_mcp_used ?? 0 },
    { step: "Tool certa", pct: m?.pct_correct_tool ?? 0 },
    { step: "Resultado certo", pct: m?.pct_correct_result ?? 0 },
  ];
}

export const statusColor = (status: TestStatus) => `var(--cobre-${status})`;

export const STATUS_LABEL: Record<TestStatus, string> = {
  pass: "Aprovada",
  partial: "Parcial",
  fail: "Falhou",
  timeout: "Timeout",
  skip: "Pulada",
};

export const TOOL_TIME_COLOR = "var(--cobre-text-muted)";

export function latencyLegend(b: BatchResult): Array<{ label: string; color: string }> {
  const present = new Set(b.test_results.map((r) => r.status));
  return [
    ...STATUS_ORDER.filter((s) => present.has(s)).map((s) => ({
      label: STATUS_LABEL[s],
      color: statusColor(s),
    })),
    { label: "Tempo na tool", color: TOOL_TIME_COLOR },
  ];
}
