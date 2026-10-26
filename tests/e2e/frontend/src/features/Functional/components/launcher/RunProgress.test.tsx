import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RunState } from "@/services/launcherApi";
import { RunProgress } from "./RunProgress";

function run(overrides: Partial<RunState> = {}): RunState {
  return {
    run_id: "r1",
    provider: "kiro-cli",
    status: "running",
    total: 3,
    completed: 1,
    current: "c2",
    batch_id: null,
    error: null,
    cancel_requested: false,
    started_at: "",
    finished_at: null,
    log: [],
    results: [],
    ...overrides,
  };
}

describe("RunProgress", () => {
  it("o botão Parar chama onStop enquanto o run está ativo", () => {
    const onStop = vi.fn();
    render(<RunProgress run={run()} stopping={false} onStop={onStop} />);
    fireEvent.click(screen.getByRole("button", { name: /Parar/ }));
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("durante a parada mostra 'Parando…' e desabilita o botão", () => {
    render(<RunProgress run={run({ cancel_requested: true })} stopping onStop={vi.fn()} />);
    expect(screen.getByText("Parando…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Parar/ })).toBeDisabled();
  });

  it("run parado não mostra o botão e avisa que a bateria não foi gravada", () => {
    render(<RunProgress run={run({ status: "cancelled" })} stopping={false} onStop={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Parar/ })).not.toBeInTheDocument();
    expect(screen.getByText(/bateria não gravada/)).toBeInTheDocument();
  });
});
