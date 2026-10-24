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

/**
 * Teste de carga — espelha o JSON de tests/e2e/load/store.py (build_record e index_entry),
 * gravado em tests/e2e/results/load/. Latências são só das chamadas ok; null quando não houve.
 */
export interface LoadStats {
  calls: number;
  ok: number;
  errors: number;
  timeouts: number;
  /** (erros + timeouts) / chamadas, de 0 a 1. */
  error_rate: number;
  throughput_cps: number;
  min_ms: number | null;
  mean_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
}

export interface LoadSeriesPoint {
  /** Início do bucket de 1 s, em segundos desde o início da carga. */
  t: number;
  calls: number;
  failed: number;
  p50_ms: number | null;
  p95_ms: number | null;
}

export interface LoadStartupEvent {
  client: number;
  kind: "preflight" | "initial" | "respawn";
  ms: number;
  warmup_ms: number | null;
  ok: boolean;
  error: string | null;
}

export interface LoadStartup {
  clients: number;
  started: number;
  failed: number;
  wall_ms: number;
  min_ms: number | null;
  mean_ms: number | null;
  max_ms: number | null;
  warmup_mean_ms: number | null;
  preflight_ms: number | null;
  respawns: number;
  events: LoadStartupEvent[];
}

export interface LoadConfigRecord {
  concurrency: number;
  duration_seconds: number;
  iterations: number | null;
  /** null = todo o mix. */
  tools: string[] | null;
  timeout_seconds: number;
  warmup?: boolean;
}

export interface LoadResourceSample {
  t: number;
  cpu_percent: number;
  rss_mb: number;
  processes: number;
}

export interface LoadResources {
  available: boolean;
  reason?: string;
  samples?: LoadResourceSample[];
  avg_cpu_percent?: number;
  peak_cpu_percent?: number;
  peak_rss_mb?: number;
  peak_processes?: number;
}

export interface LoadErrorGroup {
  tool: string;
  outcome: "error" | "timeout";
  message: string;
  count: number;
}

export interface LoadRun {
  load_id: string;
  timestamp: string;
  ended_at: string;
  version: string;
  git_commit_sha: string;
  environment: string;
  /** Interrompida por Ctrl+C na CLI: resultado parcial. */
  interrupted: boolean;
  config: LoadConfigRecord;
  server: { command?: string[]; workspace?: string[] };
  mix: {
    calls: Array<{ id: string; tool: string }>;
    excluded: Array<{ id: string; tool: string; reason: string }>;
  };
  startup: LoadStartup;
  duration_seconds: number;
  abandoned_calls: number;
  totals: LoadStats;
  per_tool: Record<string, LoadStats>;
  series: LoadSeriesPoint[];
  errors: LoadErrorGroup[];
  resources: LoadResources;
}

/** Resumo de uma carga no results/load/index.json. */
export interface LoadIndexEntry {
  load_id: string;
  timestamp: string;
  version: string;
  git_commit_sha: string;
  interrupted: boolean;
  config: Omit<LoadConfigRecord, "warmup">;
  summary: Pick<
    LoadStats,
    | "calls"
    | "ok"
    | "errors"
    | "timeouts"
    | "error_rate"
    | "throughput_cps"
    | "p50_ms"
    | "p95_ms"
    | "p99_ms"
  >;
}

export interface LoadIndex {
  runs: LoadIndexEntry[];
}
