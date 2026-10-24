/**
 * Cliente do launcher de dev (FastAPI).
 *
 * O launcher dispara os testes num provedor de IA (kiro-cli/claude) e grava a
 * bateria; o frontend consome a bateria depois via resultsApi (/data/*). Aqui
 * ficam so as chamadas de CONTROLE: detectar provedores, listar os casos
 * (biblioteca de prompts) e disparar/poll de um run.
 *
 * Base: em dev, o Vite faz proxy de /api para VITE_LAUNCHER_URL (ver
 * vite.config.ts). Assim o frontend sempre chama caminhos relativos /api/*.
 */

export const API = "api";

/** O launcher recusa POSTs sem este header (anti CSRF/DNS rebinding). */
export const LAUNCHER_HEADERS = { "X-Launcher": "1" };

export type ProviderId = "kiro-cli" | "claude";

export interface ProviderInfo {
  id: ProviderId;
  label: string;
  binary: string;
  installed: boolean;
}

export interface ProvidersResponse {
  providers: ProviderInfo[];
  default: ProviderId | null;
}

export interface CaseMeta {
  id: string;
  query: string;
  expected_tool: string | null;
  expected_tools: string[] | null;
  tags: string[];
  /** Timeout (s) da sessão do agente neste caso, já resolvido (caso > grupo > default). */
  timeout_s: number | null;
  /** Fontes que precisam existir; sem elas o caso sai como "skip". */
  requires: string[];
}

export type RunStatus = "pending" | "running" | "done" | "error" | "cancelled";

const FINISHED: ReadonlySet<RunStatus> = new Set(["done", "error", "cancelled"]);

export function isFinished(status: RunStatus): boolean {
  return FINISHED.has(status);
}

/** Resultado resumido de um caso ja terminado (transparencia incremental). */
export interface RunResultItem {
  test_id: string;
  status: string;
  expected_tool: string | null;
  actual_tool: string | null;
  mcp_used: boolean;
  correct_tool: boolean;
  correct_result: boolean;
  latency_ms: number;
  error_message: string | null;
  response_preview: string;
}

export interface RunState {
  run_id: string;
  provider: string;
  status: RunStatus;
  total: number;
  completed: number;
  current: string | null;
  batch_id: string | null;
  error: string | null;
  /** Parada pedida; o status vira "cancelled" quando o caso atual é interrompido. */
  cancel_requested: boolean;
  started_at: string;
  finished_at: string | null;
  log: string[];
  results: RunResultItem[];
}

export interface StartRunBody {
  provider?: ProviderId | null;
  tags?: string[] | null;
  case_id?: string | null;
  timeout_seconds?: number | null;
}

/** True se o launcher esta no ar (usado para habilitar os controles de disparo). */
export async function launcherHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${API}/health`, { cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchProviders(): Promise<ProvidersResponse> {
  const res = await fetch(`${API}/providers`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Falha ao detectar provedores: HTTP ${res.status}`);
  return (await res.json()) as ProvidersResponse;
}

export async function fetchCases(): Promise<CaseMeta[]> {
  const res = await fetch(`${API}/cases`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Falha ao carregar casos: HTTP ${res.status}`);
  const data = (await res.json()) as { cases: CaseMeta[] };
  return data.cases ?? [];
}

export async function startRun(body: StartRunBody): Promise<RunState> {
  const res = await fetch(`${API}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...LAUNCHER_HEADERS },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as { detail?: string };
      if (err.detail) detail = err.detail;
    } catch {
      /* ignora corpo nao-JSON */
    }
    throw new Error(`Falha ao disparar o run: ${detail}`);
  }
  return (await res.json()) as RunState;
}

export async function fetchRun(runId: string, signal?: AbortSignal): Promise<RunState> {
  const res = await fetch(`${API}/runs/${runId}`, { cache: "no-store", signal });
  if (!res.ok) throw new Error(`Falha ao consultar o run: HTTP ${res.status}`);
  return (await res.json()) as RunState;
}

/** Pede a parada do run: o caso em andamento é interrompido e os demais não rodam. */
export async function cancelRun(runId: string): Promise<RunState> {
  const res = await fetch(`${API}/runs/${runId}/cancel`, {
    method: "POST",
    headers: LAUNCHER_HEADERS,
  });
  if (!res.ok) throw new Error(`Falha ao parar o run: HTTP ${res.status}`);
  return (await res.json()) as RunState;
}

export const POLL_INTERVAL_MS = 1500;
export const POLL_MAX_MS = 30 * 60 * 1000;

/** Rejeita com AbortError quando o polling é cancelado (ex.: componente desmontado). */
export function waitOrAbort(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(signal?.reason);
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Faz polling de um run até terminar (done/error/cancelled), estourar o teto de tempo ou
 * ser cancelado pelo ``signal``. Chama onUpdate a cada tick.
 */
export async function pollRun(
  runId: string,
  onUpdate: (state: RunState) => void,
  opts: { intervalMs?: number; maxMs?: number; signal?: AbortSignal } = {},
): Promise<RunState> {
  const interval = opts.intervalMs ?? POLL_INTERVAL_MS;
  const maxMs = opts.maxMs ?? POLL_MAX_MS;
  const start = Date.now();

  for (;;) {
    const state = await fetchRun(runId, opts.signal);
    onUpdate(state);
    if (isFinished(state.status)) return state;
    if (Date.now() - start > maxMs) {
      return { ...state, status: "error", error: "Timeout de polling no frontend." };
    }
    await waitOrAbort(interval, opts.signal);
  }
}
