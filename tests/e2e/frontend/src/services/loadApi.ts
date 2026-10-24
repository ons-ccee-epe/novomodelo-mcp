/**
 * Cliente do teste de carga.
 *
 * Duas fontes, como no resto do dashboard: os runs gravados (somente leitura) vêm
 * de /data/results/load/ (index.json + <id>.json); o disparo, o progresso ao vivo e
 * o cancelamento vêm do launcher de dev, em /api/load-*.
 */
import type { LoadIndex, LoadIndexEntry, LoadRun } from "@/shared/types";
import {
  API,
  LAUNCHER_HEADERS,
  isFinished,
  waitOrAbort,
  POLL_INTERVAL_MS,
  POLL_MAX_MS,
  type RunStatus,
} from "@/services/launcherApi";

const DATA = "data/results/load";

export type LoadRunStatus = RunStatus;

export type LoadPhase = "preflight" | "starting" | "running" | "finishing";

/** Instantâneo que o motor emite uma vez por segundo (mesmos campos de LoadStats). */
export interface LoadProgress {
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
  resources: { t: number; cpu_percent: number; rss_mb: number; processes: number } | null;
}

export interface LoadRunState {
  run_id: string;
  status: LoadRunStatus;
  phase: LoadPhase | null;
  config: {
    concurrency: number;
    duration_seconds: number;
    iterations: number | null;
    tools: string[] | null;
    timeout_seconds: number;
  };
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
}

export interface LoadLimits {
  min_concurrency: number;
  max_concurrency: number;
  min_duration_seconds: number;
  max_duration_seconds: number;
  max_iterations: number;
  max_timeout_seconds: number;
  default_timeout_seconds: number;
}

export interface LoadToolsResponse {
  tools: LoadToolInfo[];
  limits: LoadLimits;
}

export interface StartLoadBody {
  concurrency: number;
  duration_seconds: number;
  iterations?: number | null;
  /** Omitido/null = todo o mix somente leitura. */
  tools?: string[] | null;
  timeout_seconds?: number | null;
}

/** index.json das cargas gravadas, mais recente primeiro; sem a pasta ainda, lista vazia. */
export async function fetchLoadIndex(): Promise<LoadIndexEntry[]> {
  const res = await fetch(`${DATA}/index.json`, { cache: "no-store" });
  if (res.status === 404) return [];
  if (!res.ok) throw new Error(`Falha ao carregar as cargas gravadas: HTTP ${res.status}`);
  const index = (await res.json()) as LoadIndex;
  return [...(index.runs ?? [])].sort((a, b) => (b.timestamp ?? "").localeCompare(a.timestamp ?? ""));
}

export async function fetchLoadRun(loadId: string): Promise<LoadRun> {
  const res = await fetch(`${DATA}/${loadId}.json`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Falha ao carregar a carga ${loadId}: HTTP ${res.status}`);
  return (await res.json()) as LoadRun;
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
