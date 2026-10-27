/** Telas da aplicação. Painel de dev local, sem perfis: toda tela é pública. */
export const ROUTES = {
  functional: { path: "/funcionais" },
  load: { path: "/carga" },
  history: { path: "/historico" },
  historyLoad: { path: "/historico/carga" },
} as const;

/** Caminho do detalhe de uma bateria no histórico. */
export function historyBatchPath(batchId: string): string {
  return `${ROUTES.history.path}/${encodeURIComponent(batchId)}`;
}

/** Caminho de uma carga gravada no histórico. */
export function historyLoadPath(loadId: string): string {
  return `${ROUTES.historyLoad.path}/${encodeURIComponent(loadId)}`;
}
