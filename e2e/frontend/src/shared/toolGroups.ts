/**
 * Mapeamento tool -> grupo. Espelha TOOL_GROUPS de e2e/novomodelo_mcp_e2e/queries/store.py.
 * Usado para filtrar a tabela de testes por grupo no frontend.
 */
export const TOOL_GROUPS: Record<string, string> = {
  bridge_check_newave: "bridge",
  bridge_check_decomp: "bridge",
  bridge_convert_newave: "bridge",
  bridge_convert_decomp: "bridge",
  bridge_compare_newave: "bridge",
  bridge_compare_decomp: "bridge",
  bridge_dashboard: "bridge",
  deck_list: "deck",
  deck_read_json: "deck",
  deck_read_parquet: "deck",
  deck_describe_parquet: "deck",
  deck_edit_json: "deck",
  deck_edit_parquet: "deck",
  deck_sql: "deck",
  docs_list: "docs",
  docs_search: "docs",
  docs_read: "docs",
  results_status: "results",
  results_convergence: "results",
  results_query: "results",
  results_list_entities: "results",
  results_policy: "results",
  results_stochastic: "results",
  schema_list: "schema",
  schema_get: "schema",
  schema_export: "schema",
  run_plan: "run",
  run_apply: "run",
  run_start: "run",
  run_status: "run",
  run_logs: "run",
  run_cancel: "run",
  case_validate: "case",
  case_summary: "case",
  case_init: "case",
  server_info: "meta",
  solver_version: "meta",
  instalar_novomodelo: "meta",
};

export function groupForTool(tool: string | null | undefined): string {
  if (!tool) return "other";
  return TOOL_GROUPS[tool] ?? "other";
}

/** Grupo de um caso: o da tool esperada (ou da primeira, se várias são aceitas). */
export function groupForCase(c: {
  grupo?: string;
  expected_tool: string | null;
  expected_tools: string[] | null;
}): string {
  if (c.grupo) return c.grupo;
  return groupForTool(c.expected_tool ?? c.expected_tools?.[0] ?? null);
}
