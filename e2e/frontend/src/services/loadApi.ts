/**
 * Cliente do teste de carga.
 *
 * Duas fontes, como no resto do dashboard: os runs gravados (somente leitura) vêm
 * de /data/results/load/ (index.json + <id>.json); o disparo, o progresso ao vivo e
 * o cancelamento vêm do launcher de dev, em /api/load-*.
 */
import type {
  AgentCaseStatus,
  AgentSelection,
  AgentSeriesPoint,
  LoadIndex,
  LoadIndexEntry,
  LoadRunMode,
  SavedLoadRun,
} from "@/shared/types";
import {
  API,
  LAUNCHER_HEADERS,
  isFinished,
  waitOrAbort,
  POLL_INTERVAL_MS,
  POLL_MAX_MS,
  type ProviderId,
  type ProviderInfo,
  type RunStatus,
} from "@/services/launcherApi";

const DATA = "data/results/load";

export type LoadRunStatus = RunStatus;

export type LoadMode = LoadRunMode;

export type LoadPhase = "preflight" | "starting" | "running" | "finishing";

export interface LoadLiveResources {
  t: number;
  cpu_percent: number;
  rss_mb: number;
  processes: number;
}

/** Instantâneo que o motor emite uma vez por segundo (mesmos campos de LoadStats). */
export interface ToolsLoadProgress {
  mode?: "tools";
  phase: LoadPhase;
  elapsed_seconds: number;
  duration_seconds: number;
  clients: { requested: number; ready: number; failed: number; respawns: number };
  calls: number;
  ok: number;
  errors: number;
  timeouts: number;
  error_rate: number;
  throughput_cps: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
  /** Buckets de 1 s mais recentes, para o gráfico ao vivo. */
  series: Array<{
    t: number;
    calls: number;
    failed: number;
    p50_ms: number | null;
    p95_ms: number | null;
  }>;
  resources: LoadLiveResources | null;
}

/** Caso em execução numa sessão do agente. */
export interface AgentInFlight {
  session: number;
  case_id: string;
  elapsed_seconds: number;
}

/** Instantâneo do modo agente; ``calls`` são execuções de caso concluídas. */
export interface AgentLoadProgress {
  mode: "agent";
  phase: LoadPhase;
  elapsed_seconds: number;
  duration_seconds: number;
  clients: { requested: number; ready: number; failed: number; respawns: number };
  sessions: { requested: number; ready: number; failed: number; running: number; finished: number };
  calls: number;
  ok: number;
  errors: number;
  timeouts: number;
  error_rate: number;
  throughput_cps: number;
  min_ms: number | null;
  mean_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  max_ms: number | null;
  /** Casos concluídos por minuto. */
  throughput_cpm: number;
  /** Só os status que ocorreram. */
  statuses: Partial<Record<AgentCaseStatus, number>>;
  /** Fração aprovada, de 0 a 1. */
  pass_rate: number;
  in_flight: AgentInFlight[];
  /** Buckets de ``series_bucket_seconds``. */
  series: AgentSeriesPoint[];
  series_bucket_seconds: number;
  resources: LoadLiveResources | null;
}

export type LoadProgress = ToolsLoadProgress | AgentLoadProgress;

export function isAgentProgress(progress: LoadProgress): progress is AgentLoadProgress {
  return progress.mode === "agent";
}

export interface ToolsRunConfig {
  mode?: "tools";
  concurrency: number;
  duration_seconds: number;
  iterations: number | null;
  tools: string[] | null;
  timeout_seconds: number;
  warmup?: boolean;
}

export interface AgentRunConfig {
  mode: "agent";
  provider: string;
  concurrency: number;
  duration_seconds: number;
  iterations: number | null;
  /** null = cada caso usa o próprio timeout. */
  timeout_seconds: number | null;
  selection: AgentSelection;
}

export interface LoadRunState {
  run_id: string;
  status: LoadRunStatus;
  phase: LoadPhase | null;
  config: ToolsRunConfig | AgentRunConfig;
  /** Id da carga gravada, quando termina com sucesso. */
  load_id: string | null;
  error: string | null;
  cancel_requested: boolean;
  started_at: string;
  finished_at: string | null;
  progress: LoadProgress | null;
  log: string[];
}

export interface LoadToolInfo {
  tool: string;
  group: string;
  calls: number;
  available: boolean;
  reason: string | null;
  /** Grava arquivos: roda numa cópia das fixtures por sessão. */
  writes: boolean;
  /** Sobe o bridge ou a CLI do solver a cada chamada. */
  heavy: boolean;
  /** Faz parte do mix padrão (as que gravam ou são pesadas ficam de fora). */
  default: boolean;
  /** Fora da carga (ex.: run_start): sempre indisponível, com o motivo em ``reason``. */
  barred: boolean;
}

export interface LoadLimits {
  min_concurrency: number;
  max_concurrency: number;
  min_duration_seconds: number;
  max_duration_seconds: number;
  max_iterations: number;
  max_timeout_seconds: number;
  /** null (modo agente) = cada caso usa o próprio timeout. */
  default_timeout_seconds: number | null;
}

export interface LoadToolsResponse {
  tools: LoadToolInfo[];
  limits: LoadLimits;
}

/** Caso do cases.yaml no modo agente; os inelegíveis vêm com o motivo. */
export interface LoadCaseInfo {
  id: string;
  query: string;
  group: string;
  tags: string[];
  expected_tool: string | null;
  expected_tools: string[] | null;
  timeout_s: number | null;
  available: boolean;
  reason: string | null;
  /** Alguma tool esperada grava (o caso roda numa cópia das fixtures). */
  writes: boolean;
  /** Alguma tool esperada sobe o bridge ou o solver. */
  heavy: boolean;
}

export interface LoadCasesResponse {
  cases: LoadCaseInfo[];
  /** ``max_concurrency`` é o teto do modo agente. */
  limits: LoadLimits;
}

/** Tudo que o formulário precisa do modo agente. */
export interface AgentCatalog {
  cases: LoadCaseInfo[];
  limits: LoadLimits;
  providers: ProviderInfo[];
  defaultProvider: ProviderId | null;
}

export type CapacityFactor = "teto do modo" | "memória" | "CPU" | "disco";

/** O que a seleção atual roda; vem do backend (``selection`` da capacidade). */
export interface CapacitySelection {
  heavy: boolean;
  writes: boolean;
  heavy_tools: string[];
  write_tools: string[];
  /** Tamanho da cópia das fixtures por sessão. */
  copy_mb: number;
  subtrees: string[];
}

/** Disco da cópia por sessão; o backend manda null quando a seleção não grava. */
export interface CapacityDisk {
  path: string;
  free_mb: number;
  copy_mb: number;
  growth: number;
  /** Cópia + folga de crescimento. */
  per_session_mb: number;
  headroom: number;
}

/**
 * Seleção que a capacidade considera: tools (lista; ausente/null = mix padrão) no modo
 * tools; um caso ou um grupo (ambos ausentes = todos os casos) no modo agente.
 */
export interface CapacityQuery {
  tools?: string[] | null;
  caseId?: string | null;
  group?: string | null;
}

/** Quantas sessões simultâneas a máquina aguenta; a memória livre é um instantâneo. */
export interface LoadCapacity {
  mode: LoadMode;
  provider: string | null;
  hard_cap: number;
  recommended: number;
  limiting_factor: CapacityFactor;
  /** ``disk`` ausente (launcher antigo) ou null (a seleção não grava): sem limite de disco. */
  limits: { hard_cap: number; cpu: number; memory: number | null; disk?: number | null };
  explanation: string;
  cpu: { logical_cores: number; reserved_cores: number };
  memory: { total_mb: number; available_mb: number } | null;
  per_session: {
    rss_mb: number;
    cpu_cores: number;
    source: "histórico" | "estimativa";
    runs: number;
    /** Ausente no launcher antigo. */
    profile?: "leve" | "pesada";
  };
  /** Ausentes no launcher antigo. */
  selection?: CapacitySelection;
  disk?: CapacityDisk | null;
  memory_headroom: number;
  warnings: string[];
}

/** Corpo do POST: só os campos do modo (valores não nulos do outro modo dão 422). */
export interface StartLoadBody {
  /** Ausente = tools. */
  mode?: LoadMode;
  concurrency: number;
  duration_seconds: number;
  iterations?: number | null;
  timeout_seconds?: number | null;
  /** Só tools: omitido/null = mix padrão (as tools com ``default``); senão, a lista explícita. */
  tools?: string[] | null;
  /** Só agent: null = primeiro instalado. */
  provider?: ProviderId | null;
  /** Só agent: no máximo um entre case_id, group e tags; nenhum = todos os elegíveis. */
  case_id?: string | null;
  group?: string | null;
  tags?: string[] | null;
}

/** index.json das cargas gravadas, mais recente primeiro; sem a pasta ainda, lista vazia. */
export async function fetchLoadIndex(): Promise<LoadIndexEntry[]> {
  const res = await fetch(`${DATA}/index.json`, { cache: "no-store" });
  if (res.status === 404) return [];
  if (!res.ok) throw new Error(`Falha ao carregar as cargas gravadas: HTTP ${res.status}`);
  const index = (await res.json()) as LoadIndex;
  return [...(index.runs ?? [])].sort((a, b) => (b.timestamp ?? "").localeCompare(a.timestamp ?? ""));
}

export async function fetchLoadRun(loadId: string): Promise<SavedLoadRun> {
  const res = await fetch(`${DATA}/${loadId}.json`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Falha ao carregar a carga ${loadId}: HTTP ${res.status}`);
  return (await res.json()) as SavedLoadRun;
}

/** FastAPI devolve `detail` como texto (409) ou lista de erros de validação (422). */
function describeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        const entry = item as { msg?: string; loc?: unknown[] };
        const field = Array.isArray(entry.loc) ? entry.loc.slice(1).join(".") : "";
        return entry.msg ? (field ? `${field}: ${entry.msg}` : entry.msg) : null;
      })
      .filter((m): m is string => Boolean(m));
    if (messages.length > 0) return messages.join("; ");
  }
  return fallback;
}

/** 404 numa rota fixa do launcher: o processo é anterior à rota (o Python não recarrega sozinho). */
const OUTDATED_LAUNCHER =
  "o launcher em execução não tem esta rota; reinicie-o (npm run dev:launcher) para carregar o código atual";

async function failure(res: Response, prefix: string): Promise<Error> {
  let detail = `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as { detail?: unknown };
    detail = describeDetail(body.detail, detail);
  } catch {
    /* corpo não-JSON */
  }
  return new Error(`${prefix}: ${detail}`);
}

export async function fetchLoadTools(): Promise<LoadToolsResponse> {
  const res = await fetch(`${API}/load-tools`, { cache: "no-store" });
  if (!res.ok) throw await failure(res, "Falha ao carregar as tools do mix de carga");
  return (await res.json()) as LoadToolsResponse;
}

export async function fetchLoadCases(): Promise<LoadCasesResponse> {
  const res = await fetch(`${API}/load-cases`, { cache: "no-store" });
  if (res.status === 404) throw new Error(`Falha ao carregar os casos da carga: ${OUTDATED_LAUNCHER}`);
  if (!res.ok) throw await failure(res, "Falha ao carregar os casos da carga");
  return (await res.json()) as LoadCasesResponse;
}

/**
 * O provedor só conta no modo agente; a memória livre muda, então busque de novo ao trocar.
 * A seleção entra na query: ``tools=a,b,c`` (tools) ou ``case_id``/``group`` (agente);
 * sem ela, vale o padrão (mix padrão / todos os casos).
 */
export async function fetchLoadCapacity(
  mode: LoadMode,
  provider?: ProviderId | null,
  selection: CapacityQuery = {},
): Promise<LoadCapacity> {
  const query = new URLSearchParams({ mode });
  if (mode === "agent") {
    if (provider) query.set("provider", provider);
    // No máximo um dos dois; o caso é o mais específico.
    if (selection.caseId) query.set("case_id", selection.caseId);
    else if (selection.group) query.set("group", selection.group);
  } else if (selection.tools && selection.tools.length > 0) {
    query.set("tools", selection.tools.join(","));
  }
  const res = await fetch(`${API}/load-capacity?${query.toString().replace(/%2C/g, ",")}`, { cache: "no-store" });
  if (res.status === 404) {
    throw new Error(`Falha ao estimar a capacidade da máquina: ${OUTDATED_LAUNCHER}`);
  }
  if (!res.ok) throw await failure(res, "Falha ao estimar a capacidade da máquina");
  return (await res.json()) as LoadCapacity;
}

export async function startLoadRun(body: StartLoadBody): Promise<LoadRunState> {
  const res = await fetch(`${API}/load-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...LAUNCHER_HEADERS },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await failure(res, "Falha ao disparar a carga");
  return (await res.json()) as LoadRunState;
}

/** Cargas desta sessão do launcher (para retomar o acompanhamento ao reabrir a tela). */
export async function fetchLoadRunStates(): Promise<LoadRunState[]> {
  const res = await fetch(`${API}/load-runs`, { cache: "no-store" });
  if (!res.ok) throw await failure(res, "Falha ao listar as cargas");
  return ((await res.json()) as { runs: LoadRunState[] }).runs ?? [];
}

export async function fetchLoadRunState(runId: string, signal?: AbortSignal): Promise<LoadRunState> {
  const res = await fetch(`${API}/load-runs/${runId}`, { cache: "no-store", signal });
  if (!res.ok) throw await failure(res, "Falha ao consultar a carga");
  return (await res.json()) as LoadRunState;
}

/** Para a carga: o launcher encerra todos os servidores MCP e não grava nada. */
export async function cancelLoadRun(runId: string): Promise<LoadRunState> {
  const res = await fetch(`${API}/load-runs/${runId}/cancel`, {
    method: "POST",
    headers: LAUNCHER_HEADERS,
  });
  if (!res.ok) throw await failure(res, "Falha ao parar a carga");
  return (await res.json()) as LoadRunState;
}

/**
 * Faz polling da carga até terminar (done/error/cancelled), estourar o teto de tempo
 * ou ser cancelado pelo ``signal``. Chama onUpdate a cada tick.
 */
export async function pollLoadRun(
  runId: string,
  onUpdate: (state: LoadRunState) => void,
  opts: { intervalMs?: number; maxMs?: number; signal?: AbortSignal } = {},
): Promise<LoadRunState> {
  const interval = opts.intervalMs ?? POLL_INTERVAL_MS;
  const maxMs = opts.maxMs ?? POLL_MAX_MS;
  const start = Date.now();

  for (;;) {
    const state = await fetchLoadRunState(runId, opts.signal);
    onUpdate(state);
    if (isFinished(state.status)) return state;
    if (Date.now() - start > maxMs) {
      return { ...state, status: "error", error: "Timeout de polling no frontend." };
    }
    await waitOrAbort(interval, opts.signal);
  }
}
