import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { makeBatch } from "@/shared/fixtures.testutil";
import type { BatchResult } from "@/shared/types";
import { History } from "./index";

const history = vi.hoisted(() => ({
  value: {} as Record<string, unknown>,
}));
const launcher = vi.hoisted(() => ({ available: true, checking: false }));

vi.mock("@/services/api/useHistory", () => ({ useHistory: () => history.value }));
vi.mock("@/services/api/useLauncher", () => ({ useLauncher: () => launcher }));

function withCounts(b: BatchResult): BatchResult {
  const passed = b.test_results.filter((r) => r.status === "pass").length;
  return { ...b, total_tests: b.test_results.length, passed };
}

const OLD = withCounts(
  makeBatch("b1", [["q1", "pass", null], ["q2", "fail", null], ["q3", "fail", null], ["q4", "fail", null], ["q5", "fail", null]], {
    timestamp: "2026-01-01T10:00:00",
    conjunto: "todos",
  }),
);
const MID = withCounts(
  makeBatch("b2", [["q1", "pass", null], ["q2", "pass", null], ["q3", "pass", null], ["q4", "pass", null], ["q5", "fail", null]], {
    timestamp: "2026-01-02T11:30:00",
    conjunto: "todos",
  }),
);
const GRP = withCounts(
  makeBatch("b3", [["q1", "pass", null], ["q2", "pass", null]], {
    timestamp: "2026-01-03T09:05:00",
    conjunto: "grupo:deck",
  }),
);
const BATCHES = [GRP, MID, OLD];

function setup(over: Record<string, unknown> = {}) {
  const toggleBaseline = vi.fn(async () => {});
  history.value = {
    batches: BATCHES,
    baselines: {},
    loading: false,
    error: null,
    reload: vi.fn(),
    toggleBaseline,
    ...over,
  };
  return toggleBaseline;
}

function renderAt(path = "/historico") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/historico" element={<History />} />
        <Route path="/historico/:batchId" element={<History />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  launcher.available = true;
});

describe("History", () => {
  it("lista os cards do mais recente ao mais antigo, com tag, contagem e delta", () => {
    setup();
    renderAt();
    const cards = screen.getAllByRole("listitem");
    expect(cards.map((c) => c.getAttribute("data-batch-id"))).toEqual(["b3", "b2", "b1"]);
    const mid = cards[1];
    expect(within(mid).getByText("Esteira completa")).toBeInTheDocument();
    expect(within(mid).getByText(/4\/5 aprovadas · 80,0%/)).toBeInTheDocument();
    const delta = within(mid).getByText(/\+60,0 pp/);
    expect(delta.textContent).toContain("▲");
    expect(delta).toHaveAttribute("data-trend", "up");
    expect(delta).toHaveAttribute("title", "vs anterior b1");
    expect(within(cards[0]).getByText("—")).toHaveAttribute("data-trend", "none");
    expect(within(mid).getByText("02/01 11:30")).toBeInTheDocument();
  });

  it("formata delta negativo com sinal unicode e vírgula", () => {
    setup({ batches: [OLD, MID], baselines: { todos: "b2" } });
    renderAt();
    const card = screen.getAllByRole("listitem").find((c) => c.getAttribute("data-batch-id") === "b1")!;
    const delta = within(card).getByText(/pp/);
    expect(delta.textContent).toBe("▼ −60,0 pp");
    expect(delta).toHaveAttribute("data-trend", "down");
    expect(delta).toHaveAttribute("title", "vs baseline b2");
  });

  it("filtra por conjunto", () => {
    setup();
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: "Grupo deck" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Todos" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("a estrela chama toggleBaseline", () => {
    const toggle = setup({ baselines: { todos: "b1" } });
    renderAt();
    const star = screen.getByRole("button", { name: /baseline.*b2/i });
    fireEvent.click(star);
    expect(toggle).toHaveBeenCalledWith(MID);
    const filled = screen.getByRole("button", { name: /remover baseline.*b1/i });
    expect(filled).toHaveAttribute("aria-pressed", "true");
  });

  it("estrela desabilitada com o launcher offline", () => {
    const toggle = setup();
    launcher.available = false;
    renderAt();
    const star = screen.getByRole("button", { name: /baseline.*b2/i });
    expect(star).toBeDisabled();
    expect(star).toHaveAttribute("title", "Suba o launcher para alterar a baseline");
    fireEvent.click(star);
    expect(toggle).not.toHaveBeenCalled();
  });

  it("mostra a recusa do launcher ao alternar a baseline", async () => {
    setup({
      toggleBaseline: vi.fn(async () => {
        throw new Error("launcher recusou");
      }),
    });
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: /baseline.*b2/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("launcher recusou");
  });

  it("abrir /historico/<id> seleciona aquela bateria", () => {
    setup();
    renderAt("/historico/b1");
    const selected = screen.getAllByRole("listitem").filter((c) => c.getAttribute("aria-current") === "true");
    expect(selected.map((c) => c.getAttribute("data-batch-id"))).toEqual(["b1"]);
    expect(screen.getByRole("region", { name: "Dashboard da bateria" })).toHaveTextContent("b1");
  });

  it("sem parâmetro seleciona a mais recente e clicar no card navega", async () => {
    setup();
    renderAt();
    expect(screen.getByRole("region", { name: "Dashboard da bateria" })).toHaveTextContent("b3");
    fireEvent.click(within(screen.getAllByRole("listitem")[2]).getByRole("link"));
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Dashboard da bateria" })).toHaveTextContent("b1"),
    );
  });

  it("histórico vazio e erro", () => {
    setup({ batches: [] });
    const { unmount } = renderAt();
    expect(screen.getByText("Nenhuma bateria gravada")).toBeInTheDocument();
    unmount();
    setup({ batches: [], error: "falhou ao ler" });
    renderAt();
    expect(screen.getByText(/falhou ao ler/)).toBeInTheDocument();
  });
});
