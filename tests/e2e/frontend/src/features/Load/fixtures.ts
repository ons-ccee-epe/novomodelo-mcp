import type { LoadCapacity, LoadCaseInfo, LoadToolInfo } from "@/services/loadApi";
import type { AgentLoadRun, AgentStats, LoadRun, LoadSandbox, LoadStats } from "@/shared/types";

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

export function agentStats(overrides: Partial<AgentStats> = {}): AgentStats {
  return {
    calls: 10,
    ok: 9,
    errors: 0,
    timeouts: 1,
    error_rate: 0.1,
    throughput_cps: 0.02,
    min_ms: 8000,
    mean_ms: 12000,
    p50_ms: 11000,
    p95_ms: 20000,
    p99_ms: 22000,
    max_ms: 23000,
    throughput_cpm: 1.3,
    statuses: { pass: 8, partial: 1, fail: 0, timeout: 1, error: 0 },
    pass_rate: 0.8,
    tool_calls_mean: 2.5,
    mcp_calls_mean: 2.2,
    ...overrides,
  };
}

export function makeAgentLoadRun(overrides: Partial<AgentLoadRun> = {}): AgentLoadRun {
  return {
    mode: "agent",
    load_id: "20261024_110000_abc1234",
    timestamp: "2026-10-24T11:00:00",
    ended_at: "2026-10-24T11:03:00",
    version: "0.18.0",
    git_commit_sha: "abc1234def5678",
    environment: "local",
    interrupted: false,
    config: {
      mode: "agent",
      provider: "claude",
      concurrency: 2,
      duration_seconds: 120,
      iterations: null,
      timeout_seconds: null,
      selection: { case_id: null, group: "docs", tags: null },
    },
    agent: { provider: "claude", label: "Claude Code", binary: "claude", denied_tools: ["deck_edit_json"] },
    server: { command: ["python", "-m", "novomodelo_mcp"], workspace: [] },
    cases: {
      selection: "grupo docs",
      selected: [{ id: "docs_search#a", group: "docs", tool: "docs_search" }],
      excluded: [{ id: "run_start#x", tool: "run_start", reason: "dispara o solver" }],
    },
    sessions: {
      requested: 2,
      started: 2,
      failed: 0,
      setup_ms: 9000,
      events: [
        { session: 0, ok: true, ms: 4000, error: null, executions: 5 },
        { session: 1, ok: true, ms: 4200, error: null, executions: 5 },
      ],
    },
    duration_seconds: 120,
    abandoned_calls: 0,
    series_bucket_seconds: 5,
    totals: agentStats(),
    per_case: {
      "docs_search#a": { ...agentStats({ calls: 6 }), group: "docs" },
      "docs_list#b": {
        ...agentStats({ calls: 4, statuses: { pass: 4, partial: 0, fail: 0, timeout: 0, error: 0 } }),
        group: "docs",
      },
    },
    series: [
      { t: 0, calls: 1, failed: 0, passed: 1, p50_ms: 9000, p95_ms: 9000 },
      { t: 5, calls: 2, failed: 1, passed: 1, p50_ms: 12000, p95_ms: 20000 },
    ],
    errors: [
      { case_id: "docs_search#a", status: "timeout", outcome: "timeout", message: "estourou 90 s", count: 1 },
    ],
    resources: { available: false, reason: "psutil não instalado" },
    ...overrides,
  };
}

/** Tool do catálogo do launcher: por padrão leve, só leitura e no mix padrão. */
export function toolInfo(overrides: Partial<LoadToolInfo> = {}): LoadToolInfo {
  return {
    tool: "docs_list",
    group: "docs",
    calls: 1,
    available: true,
    reason: null,
    writes: false,
    heavy: false,
    default: true,
    barred: false,
    ...overrides,
  };
}

/** Caso do cases.yaml no modo agente: por padrão elegível, leve e só leitura. */
export function caseInfo(overrides: Partial<LoadCaseInfo> = {}): LoadCaseInfo {
  return {
    id: "c",
    query: "pergunta",
    group: "docs",
    tags: [],
    expected_tool: "docs_search",
    expected_tools: null,
    timeout_s: 90,
    available: true,
    reason: null,
    writes: false,
    heavy: false,
    ...overrides,
  };
}

/** Capacidade do modo tools com seleção leve e só leitura (sem disco). */
export function makeCapacity(overrides: Partial<LoadCapacity> = {}): LoadCapacity {
  return {
    mode: "tools",
    provider: null,
    hard_cap: 32,
    recommended: 6,
    limiting_factor: "CPU",
    limits: { hard_cap: 32, cpu: 6, memory: 40, disk: null },
    explanation: "≈ 6 sessões: limitado por CPU (6 núcleos úteis ÷ 1 núcleo/sessão).",
    cpu: { logical_cores: 8, reserved_cores: 2 },
    memory: { total_mb: 16000, available_mb: 8000 },
    per_session: { rss_mb: 200, cpu_cores: 1, source: "estimativa", runs: 0, profile: "leve" },
    selection: { heavy: false, writes: false, heavy_tools: [], write_tools: [], copy_mb: 0, subtrees: [] },
    disk: null,
    memory_headroom: 0.25,
    warnings: [],
    ...overrides,
  };
}

/** Cópia por sessão (sandbox) de um registro que tinha tools que gravam. */
export function makeSandbox(overrides: Partial<LoadSandbox> = {}): LoadSandbox {
  return {
    enabled: true,
    subtrees: ["newave/cobre-caso-reduzido"],
    copy_mb: 23.4,
    sessions: 2,
    copy_ms_mean: 180,
    copy_ms_max: 240,
    final_mb_max: 24.1,
    ...overrides,
  };
}
