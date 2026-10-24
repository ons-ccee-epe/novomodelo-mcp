import type { LoadRun, LoadStats } from "@/shared/types";

/** Dados de teste do teste de carga (usados só pelos testes da área). */
export function stats(overrides: Partial<LoadStats> = {}): LoadStats {
  return {
    calls: 100,
    ok: 100,
    errors: 0,
    timeouts: 0,
    error_rate: 0,
    throughput_cps: 10,
    min_ms: 10,
    mean_ms: 40,
    p50_ms: 30,
    p95_ms: 90,
    p99_ms: 120,
    max_ms: 150,
    ...overrides,
  };
}

export function makeLoadRun(overrides: Partial<LoadRun> = {}): LoadRun {
  return {
    load_id: "20261024_100000_abc1234",
    timestamp: "2026-10-24T10:00:00",
    ended_at: "2026-10-24T10:00:30",
    version: "0.18.0",
    git_commit_sha: "abc1234def5678",
    environment: "local",
    interrupted: false,
    config: {
      concurrency: 2,
      duration_seconds: 10,
      iterations: null,
      tools: null,
      timeout_seconds: 60,
    },
    server: { command: ["python", "-m", "novomodelo_mcp"], workspace: [] },
    mix: {
      calls: [{ id: "docs_list#todas", tool: "docs_list" }],
      excluded: [{ id: "deck_list#x", tool: "deck_list", reason: "fonte ausente ou vazia: x" }],
    },
    startup: {
      clients: 2,
      started: 2,
      failed: 0,
      wall_ms: 8000,
      min_ms: 5700,
      mean_ms: 5800,
      max_ms: 5900,
      warmup_mean_ms: 2700,
      preflight_ms: 8800,
      respawns: 0,
      events: [],
    },
    duration_seconds: 10,
    abandoned_calls: 0,
    totals: stats(),
    per_tool: {
      deck_list: stats({ calls: 40, p95_ms: 70 }),
      docs_search: stats({ calls: 60, p95_ms: 110 }),
    },
    series: [
      { t: 0, calls: 8, failed: 0, p50_ms: 30, p95_ms: 80 },
      { t: 1, calls: 12, failed: 1, p50_ms: 32, p95_ms: 95 },
    ],
    errors: [],
    resources: { available: false, reason: "psutil não instalado" },
    ...overrides,
  };
}
