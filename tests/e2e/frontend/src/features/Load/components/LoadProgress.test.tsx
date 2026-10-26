import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { LoadRunState, ToolsLoadProgress as Progress } from "@/services/loadApi";
import { LoadProgress } from "./LoadProgress";

function progress(overrides: Partial<Progress> = {}): Progress {
  return {
    phase: "running",
    elapsed_seconds: 4,
    duration_seconds: 10,
    clients: { requested: 4, ready: 4, failed: 0, respawns: 0 },
    calls: 120,
    ok: 118,
    errors: 1,
    timeouts: 1,
    error_rate: 2 / 120,
    throughput_cps: 30,
    p50_ms: 35,
    p95_ms: 110,
    p99_ms: 160,
    max_ms: 200,
    series: [],
    resources: null,
    ...overrides,
  };
}

function run(overrides: Partial<LoadRunState> = {}): LoadRunState {
  return {
    run_id: "r1",
    status: "running",
    phase: "running",
    config: { concurrency: 4, duration_seconds: 10, iterations: null, tools: null, timeout_seconds: 60 },
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

describe("LoadProgress", () => {
  it("o botão Parar chama onStop enquanto a carga está ativa", () => {
    const onStop = vi.fn();
    render(<LoadProgress run={run()} stopping={false} onStop={onStop} />);
    fireEvent.click(screen.getByRole("button", { name: /Parar/ }));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("durante a parada mostra Parando e desabilita o botão", () => {
    render(<LoadProgress run={run({ cancel_requested: true })} stopping onStop={vi.fn()} />);
    expect(screen.getByText("Parando…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Parar/ })).toBeDisabled();
  });

  it("mostra as métricas ao vivo durante a carga", () => {
    render(<LoadProgress run={run()} stopping={false} onStop={vi.fn()} />);
    expect(screen.getByText("Carga em andamento…")).toBeInTheDocument();
    const live = screen.getByLabelText("Métricas ao vivo");
    expect(live).toHaveTextContent("120");
    expect(live).toHaveTextContent("30.0/s");
    expect(live).toHaveTextContent("1.7%");
    expect(live).toHaveTextContent("110 ms");
    expect(live).toHaveTextContent("Sessões abertas 4/4");
    expect(screen.getByText(/4 sessões simultâneas/)).toBeInTheDocument();
  });

  it("na abertura das sessões mostra quantas já estão prontas", () => {
    const starting = run({
      phase: "starting",
      progress: progress({
        phase: "starting",
        calls: 0,
        clients: { requested: 4, ready: 1, failed: 0, respawns: 0 },
      }),
    });
    render(<LoadProgress run={starting} stopping={false} onStop={vi.fn()} />);
    expect(screen.getByText("Abrindo as sessões (1/4)…")).toBeInTheDocument();
    expect(screen.queryByLabelText("Métricas ao vivo")).not.toBeInTheDocument();
  });

  it("no pré-voo avisa que valida o mix", () => {
    render(
      <LoadProgress
        run={run({ phase: "preflight", progress: null })}
        stopping={false}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByText(/Validando o mix/)).toBeInTheDocument();
  });

  it("carga parada não mostra o botão e avisa que nada foi gravado", () => {
    render(<LoadProgress run={run({ status: "cancelled" })} stopping={false} onStop={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Parar/ })).not.toBeInTheDocument();
    expect(screen.getByText(/carga não gravada/)).toBeInTheDocument();
  });

  it("erro do motor aparece na tela", () => {
    render(
      <LoadProgress
        run={run({ status: "error", error: "o servidor MCP não iniciou: x" })}
        stopping={false}
        onStop={vi.fn()}
      />,
    );
    expect(screen.getByText("o servidor MCP não iniciou: x")).toBeInTheDocument();
  });
});
