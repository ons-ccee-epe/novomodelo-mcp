import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { AgentLoadProgress, LoadRunState } from "@/services/loadApi";
import { LoadProgress } from "./LoadProgress";

function progress(overrides: Partial<AgentLoadProgress> = {}): AgentLoadProgress {
  return {
    mode: "agent",
    phase: "running",
    elapsed_seconds: 40,
    duration_seconds: 120,
    clients: { requested: 4, ready: 4, failed: 0, respawns: 0 },
    sessions: { requested: 4, ready: 4, failed: 0, running: 3, finished: 1 },
    calls: 12,
    ok: 11,
    errors: 0,
    timeouts: 1,
    error_rate: 1 / 12,
    throughput_cps: 0.03,
    min_ms: 8000,
    mean_ms: 12000,
    p50_ms: 11000,
    p95_ms: 20000,
    p99_ms: 22000,
    max_ms: 23000,
    throughput_cpm: 1.8,
    statuses: { pass: 9, partial: 1, timeout: 1 },
    pass_rate: 0.75,
    in_flight: [{ session: 2, case_id: "docs_search#a", elapsed_seconds: 7.5 }],
    series: [{ t: 0, calls: 2, failed: 0, passed: 2, p50_ms: 9000, p95_ms: 9500 }],
    series_bucket_seconds: 5,
    resources: null,
    ...overrides,
  };
}

function run(overrides: Partial<LoadRunState> = {}): LoadRunState {
  return {
    run_id: "r1",
    status: "running",
    phase: "running",
    config: {
      mode: "agent",
      provider: "claude",
      concurrency: 4,
      duration_seconds: 120,
      iterations: null,
      timeout_seconds: null,
      selection: { case_id: null, group: null, tags: null },
    },
    load_id: null,
    error: null,
    cancel_requested: false,
    started_at: "",
    finished_at: null,
    progress: progress(),
    log: [],
    ...overrides,
  };
}

describe("LoadProgress no modo agente", () => {
  it("mostra sessões, execuções, aprovação, vazão em casos/min e os casos em curso", () => {
    render(<LoadProgress run={run()} stopping={false} onStop={vi.fn()} />);

    expect(screen.getByText("Carga em andamento…")).toBeInTheDocument();
    expect(screen.getByText(/claude · 4 sessões simultâneas/)).toBeInTheDocument();
    const live = screen.getByLabelText("Métricas ao vivo");
    expect(live).toHaveTextContent("4/4 abertas · 3 em execução · 1 concluídas");
    expect(live).toHaveTextContent("Execuções 12");
    expect(live).toHaveTextContent("Aprovação 75.0%");
    expect(live).toHaveTextContent("1.8 casos/min");
    expect(live).toHaveTextContent("Erros e timeouts 1");
    expect(live).toHaveTextContent("20.00 s");

    const inFlight = screen.getByLabelText("Casos em curso");
    expect(inFlight).toHaveTextContent("sessão 2");
    expect(inFlight).toHaveTextContent("docs_search#a");
    expect(inFlight).toHaveTextContent("7.5 s");
    expect(screen.getByText("Casos concluídos por bucket de 5 s")).toBeInTheDocument();
  });

  it("no pré-voo avisa que não gasta tokens", () => {
    render(
      <LoadProgress
        run={run({ phase: "preflight", progress: progress({ phase: "preflight", calls: 0 }) })}
        stopping={false}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByText("Pré-voo: casos e servidor MCP (sem tokens)…")).toBeInTheDocument();
    expect(screen.queryByLabelText("Métricas ao vivo")).not.toBeInTheDocument();
  });

  it("na abertura das sessões mostra quantas já estão prontas", () => {
    render(
      <LoadProgress
        run={run({
          phase: "starting",
          progress: progress({
            phase: "starting",
            calls: 0,
            sessions: { requested: 4, ready: 1, failed: 0, running: 0, finished: 0 },
          }),
        })}
        stopping={false}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByText("Abrindo as sessões (1/4)…")).toBeInTheDocument();
  });

  it("ao fim da janela espera os casos em curso", () => {
    render(
      <LoadProgress
        run={run({ phase: "finishing", progress: progress({ phase: "finishing" }) })}
        stopping={false}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByText("Aguardando 1 caso(s) em curso…")).toBeInTheDocument();
  });
});
