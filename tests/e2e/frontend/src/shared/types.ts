/**
 * Contrato de dados — espelha os dataclasses de tests/e2e/queries/models.py
 * e o formato persistido por tests/e2e/queries/store.py.
 *
 * Fonte de verdade: os JSON gravados pelo ResultStore. Nenhum HTML e gerado;
 * o frontend le estes tipos de /data/results/* e /data/metrics/*.
 */

export type TestStatus = "pass" | "partial" | "fail" | "skip" | "timeout";

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  tool_id?: string | null;
}

export interface TestResult {
  test_id: string;
  query: string;
  expected_tool: string | null;
  expected_tools: string[] | null;
  actual_tool: string | null;
  all_tool_calls: ToolCall[];
  status: TestStatus;
  latency_ms: number;
  tool_latency_ms: number | null;
  mcp_used: boolean;
  correct_tool: boolean;
  correct_result: boolean;
  agent_response: string;
  error_message: string | null;
  tags: string[];
  validation_checks: Array<Record<string, unknown>>;
}

export interface BatchMetrics {
  pct_mcp_used: number;
  pct_correct_tool: number;
  pct_correct_result: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  passed_full?: number;
  passed_mcp_only?: number;
  failed_no_mcp?: number;
  failed_wrong_tool?: number;
  failed_other?: number;
}

export interface TagMetrics {
  total: number;
  passed: number;
  failed: number;
  mcp_used: number;
  correct_tool: number;
}

export interface GroupMetrics {
  total: number;
  pct_pass: number;
  pct_mcp_used: number;
  pct_correct_tool: number;
  avg_latency_ms: number;
}

export interface BatchResult {
  batch_id: string;
  timestamp: string;
  cobre_mcp_version: string;
  git_commit_sha: string;
  environment: string;
  total_tests: number;
  passed: number;
  partial: number;
  failed: number;
  skipped: number;
  timeout: number;
  test_results: TestResult[];
  metrics: BatchMetrics;
  metrics_by_tag: Record<string, TagMetrics>;
  metrics_by_group: Record<string, GroupMetrics>;
}

/** Resumo de uma bateria no index.json (ResultStore._update_index). */
export interface BatchIndexEntry {
  batch_id: string;
  timestamp: string;
  version: string;
  summary: {
    total: number;
    passed: number;
    failed: number;
    skipped: number;
    timeout: number;
  };
}

export interface BatchIndex {
  batches: BatchIndexEntry[];
}

/** Uma linha do metrics/history.jsonl (ResultStore.append_metrics). */
export interface MetricsHistoryRecord {
  batch_id: string;
  timestamp: string;
  pct_mcp_used: number;
  pct_correct_tool: number;
  pct_correct_result: number;
  avg_latency_ms: number;
  metrics_by_tag?: Record<string, Record<string, number>>;
  metrics_by_group?: Record<string, Record<string, number>>;
  alerts?: Record<string, boolean>;
}
