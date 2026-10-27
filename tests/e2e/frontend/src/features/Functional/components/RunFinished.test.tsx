import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { RunState, RunStatus } from "@/services/launcherApi";
import { RunFinished } from "./RunFinished";

function runOf(status: RunStatus, batch_id: string | null = "b1"): RunState {
  return {
    run_id: "r1", provider: "claude", status, total: 1, completed: 1, current: null,
    batch_id, error: null, cancel_requested: false, started_at: "", finished_at: null,
    log: [], results: [],
  };
}

function renderIt(run: RunState) {
  return render(
    <MemoryRouter>
      <Routes>
        <Route path="/" element={<RunFinished run={run} />} />
        <Route path="/historico/:id" element={<div>detalhe</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("RunFinished", () => {
  it("com done e batch_id mostra só o botão de ver resultados", () => {
    renderIt(runOf("done"));
    expect(screen.getByRole("button", { name: "Ver resultados no Histórico" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /baseline/i })).toBeNull();
  });

  it.each<[RunStatus, string | null]>([
    ["cancelled", "b1"],
    ["error", "b1"],
    ["done", null],
    ["running", "b1"],
  ])("com %s e batch_id %s não mostra nada", (status, id) => {
    const { container } = renderIt(runOf(status, id));
    expect(container).toBeEmptyDOMElement();
  });

  it("Ver resultados no Histórico navega para o detalhe da bateria", () => {
    renderIt(runOf("done"));
    fireEvent.click(screen.getByRole("button", { name: "Ver resultados no Histórico" }));
    expect(screen.getByText("detalhe")).toBeInTheDocument();
  });
});
