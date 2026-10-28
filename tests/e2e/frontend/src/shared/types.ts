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
  mcp_version: string;
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
  conjunto?: string | null;
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
  conjunto?: string;
}

export interface BatchIndex{
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
  /** Cópia das fixtures da sessão; ausente nos registros antigos ou sem sandbox. */
  copy_ms?: number | null;
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
  /** Ausente nos registros antigos (= tools). */
  mode?: "tools";
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
  /** Ausente nos registros antigos (= tools). */
  mode?: "tools";
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
  sandbox?: LoadSandbox;
}

/**
 * Cópia das fixtures por sessão ("sandbox") das tools/casos que gravam arquivos.
 * Ausente nos registros anteriores ao recurso; ``enabled: false`` = nada foi copiado.
 */
export interface LoadSandbox {
  enabled: boolean;
  subtrees?: string[];
  copy_mb?: number;
  sessions?: number;
  copy_ms_mean?: number | null;
  copy_ms_max?: number | null;
  final_mb_max?: number | null;
}

/** Resultado de um caso no modo agente. */
export type AgentCaseStatus = "pass" | "partial" | "fail" | "timeout" | "error";

/** Estatísticas do modo agente: ``calls`` são execuções de caso; latência só das completas. */
export interface AgentStats extends LoadStats {
  /** Casos concluídos por minuto. */
  throughput_cpm: number;
  statuses: Record<AgentCaseStatus, number>;
  /** Fração de execuções aprovadas, de 0 a 1. */
  pass_rate: number;
  tool_calls_mean: number | null;
  mcp_calls_mean: number | null;
}

export interface AgentSeriesPoint extends LoadSeriesPoint {
  passed: number;
}

export interface AgentSelection {
  case_id: string | null;
  group: string | null;
  tags: string[] | null;
}

export interface AgentConfigRecord {
  mode: "agent";
  provider: string;
  concurrency: number;
  duration_seconds: number;
  iterations: number | null;
  /** null = cada caso usa o próprio timeout. */
  timeout_seconds: number | null;
  selection: AgentSelection;
}

export interface AgentErrorGroup {
  case_id: string;
  status: string;
  outcome: string;
  message: string;
  count: number;
}

export interface AgentLoadRun {
  mode: "agent";
  load_id: string;
  timestamp: string;
  ended_at: string;
  version: string;
  git_commit_sha: string;
  environment: string;
  interrupted: boolean;
  config: AgentConfigRecord;
  agent: {
    provider: string;
    label: string;
    binary: string;
    /** Tools de escrita negadas ao claude (vazio no kiro). */
    denied_tools: string[];
  };
  server: { command?: string[]; workspace?: string[] };
  cases: {
    /** Ex.: "grupo docs". */
    selection: string;
    selected: Array<{ id: string; group: string; tool: string | null }>;
    excluded: Array<{ id: string; tool: string | null; reason: string }>;
  };
  sessions: {
    requested: number;
    started: number;
    failed: number;
    setup_ms: number;
    events: Array<{
      session: number;
      ok: boolean;
      ms: number;
      error: string | null;
      executions: number;
      /** Cópia das fixtures da sessão; ausente nos registros antigos ou sem sandbox. */
      copy_ms?: number | null;
    }>;
  };
  duration_seconds: number;
  abandoned_calls: number;
  series_bucket_seconds: number;
  totals: AgentStats;
  per_case: Record<string, AgentStats & { group: string }>;
  series: AgentSeriesPoint[];
  errors: AgentErrorGroup[];
  resources: LoadResources;
  sandbox?: LoadSandbox;
}

/** Carga gravada de qualquer modo; os registros antigos (sem ``mode``) são do modo tools. */
export type SavedLoadRun = LoadRun | AgentLoadRun;

export function isAgentRun(run: SavedLoadRun): run is AgentLoadRun {
  return run.mode === "agent";
}

export type LoadRunMode = "tools" | "agent";

/** Configuração resumida no index.json: campos de tools ou do agente, conforme ``mode``. */
export interface LoadIndexConfig {
  mode?: LoadRunMode;
  concurrency: number;
  duration_seconds: number;
  iterations: number | null;
  timeout_seconds: number | null;
  /** Só tools. */
  tools?: string[] | null;
  /** Só agent. */
  provider?: string;
  selection?: AgentSelection;
}

/** Resumo de uma carga no results/load/index.json. */
export interface LoadIndexEntry {
  /** Ausente nas entradas antigas (= tools). */
  mode?: LoadRunMode;
  load_id: string;
  timestamp: string;
  version: string;
  git_commit_sha: string;
  interrupted: boolean;
  config: LoadIndexConfig;
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
  > & {
    /** Só agent. */
    throughput_cpm?: number;
    pass_rate?: number;
  };
}

export function indexEntryMode(entry: LoadIndexEntry): LoadRunMode {
  return entry.mode ?? entry.config.mode ?? "tools";
}

export interface LoadIndex {
  runs: LoadIndexEntry[];
}
