/** Telas da aplicação. Painel de dev local, sem perfis: toda tela é pública. */
export const ROUTES = {
  functional: { path: "/funcionais" },
  load: { path: "/carga" },
  history: { path: "/historico" },
} as const;

/** Caminho do detalhe de uma bateria no histórico. */
export function historyBatchPath(batchId: string): string {
  return `${ROUTES.history.path}/${encodeURIComponent(batchId)}`;
}
