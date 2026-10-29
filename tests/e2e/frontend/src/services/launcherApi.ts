/**
 * Pontos comuns do launcher de dev (FastAPI): base das rotas, header dos POSTs, saúde e
 * espera cancelável. As rodadas ficam em `@/data/rodada`; as cargas em `loadApi`.
 *
 * Base: em dev, o Vite faz proxy de /api e /data para VITE_LAUNCHER_URL (ver
 * vite.config.ts). Assim o frontend sempre chama caminhos relativos.
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

/** Os agentes que `POST /api/load-runs` aceita no modo agente (o padrão do launcher é o primeiro). */
export const PROVEDORES_DA_CARGA: ProviderInfo[] = [
  { id: "claude", label: "Claude Code", binary: "claude", installed: true },
  { id: "kiro-cli", label: "Kiro", binary: "kiro-cli", installed: true },
];

export type RunStatus = "pending" | "running" | "done" | "error" | "cancelled";

const FINISHED: ReadonlySet<RunStatus> = new Set(["done", "error", "cancelled"]);

export function isFinished(status: RunStatus): boolean {
  return FINISHED.has(status);
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
