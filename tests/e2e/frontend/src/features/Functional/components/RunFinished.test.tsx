import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunState, RunStatus } from "@/services/launcherApi";
import { makeBatch } from "@/shared/fixtures.testutil";
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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RunFinished", () => {
  it("com done e batch_id mostra os dois botões", () => {
    renderIt(runOf("done"));
    expect(screen.getByRole("button", { name: "Resumo de resultados" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Definir como baseline" })).toBeInTheDocument();
  });

  it.each<[RunStatus, string | null]>([
    ["cancelled", "b1"],
    ["error", "b1"],
    ["done", null],
    ["running", "b1"],
  ])("com %s e batch_id %s não mostra nenhum", (status, id) => {
    const { container } = renderIt(runOf(status, id));
    expect(container).toBeEmptyDOMElement();
  });

  it("Resumo de resultados navega para o detalhe da bateria", () => {
    renderIt(runOf("done"));
    fireEvent.click(screen.getByRole("button", { name: "Resumo de resultados" }));
    expect(screen.getByText("detalhe")).toBeInTheDocument();
  });

  it("Definir como baseline grava pelo conjunto da bateria", async () => {
    const batch = makeBatch("b1", [["q1", "pass", "deck_list"]], { conjunto: "pergunta:q1" });
    const mock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "PUT") return { ok: true, status: 200, json: async () => ({}) } as Response;
      if (url === "data/results/b1.json") {
        return { ok: true, status: 200, json: async () => batch, text: async () => JSON.stringify(batch) } as Response;
      }
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    });
    vi.stubGlobal("fetch", mock);
    renderIt(runOf("done"));

    fireEvent.click(screen.getByRole("button", { name: "Definir como baseline" }));

    expect(await screen.findByText("Baseline definida")).toBeInTheDocument();
    const put = mock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe("api/baselines/pergunta%3Aq1");
    expect(JSON.parse(put[1]!.body as string)).toEqual({ batch_id: "b1" });
  });

  it("mostra o erro da baseline ao lado do botão", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response),
    );
    renderIt(runOf("done"));
    fireEvent.click(screen.getByRole("button", { name: "Definir como baseline" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Definir como baseline" })).toBeEnabled(),
    );
  });
});
