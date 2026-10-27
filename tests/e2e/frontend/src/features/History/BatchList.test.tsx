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

const sideItems = () => within(screen.getByRole("complementary")).getAllByRole("listitem");

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
    const cards = sideItems();
    expect(cards.map((c) => c.getAttribute("data-batch-id"))).toEqual(["b3", "b2", "b1"]);
    const mid = cards[1];
    expect(within(mid).getByText("Esteira")).toBeInTheDocument();
    expect(within(mid).getByText(/^4\/5 · /)).toBeInTheDocument();
    expect(within(mid).getByText("80%")).toHaveAttribute("data-band", "good");
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
    const card = sideItems().find((c) => c.getAttribute("data-batch-id") === "b1")!;
    const delta = within(card).getByText(/pp/);
    expect(delta.textContent).toBe("▼ −60,0 pp");
    expect(delta).toHaveAttribute("data-trend", "down");
    expect(delta).toHaveAttribute("title", "vs baseline b2");
  });

  it("filtra por conjunto no dropdown, com a contagem de cada um", () => {
    setup();
    renderAt();
    const select = screen.getByLabelText("Filtrar por conjunto");
    expect(within(select).getByRole("option", { name: "Todas (3)" })).toBeInTheDocument();
    expect(within(select).getByRole("option", { name: "Esteira completa (2)" })).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "grupo:deck" } });
    expect(sideItems()).toHaveLength(1);
    expect(screen.getByText("1/3")).toBeInTheDocument();
    fireEvent.change(select, { target: { value: "" } });
    expect(sideItems()).toHaveLength(3);
  });

  it("bateria de uma pergunta só vira Avulsa, com o texto da pergunta no dropdown", () => {
    const single = withCounts(
      makeBatch("b4", [["q9", "pass", null]], {
        timestamp: "2026-01-04T09:00:00",
        conjunto: "pergunta:q9",
      }),
    );
    single.test_results[0].query = "Qual a versão do servidor?";
    setup({ batches: [single, ...BATCHES] });
    renderAt();
    const tag = within(sideItems()[0]).getByText("Avulsa");
    expect(tag).toHaveAttribute("title", "Qual a versão do servidor?");
    const select = screen.getByLabelText("Filtrar por conjunto");
    const group = within(select).getByRole("group", { name: "Perguntas avulsas" });
    expect(within(group).getByRole("option", { name: "Qual a versão do servidor? (1)" })).toBeInTheDocument();
    expect(
      within(within(select).getByRole("group", { name: "Grupos" })).getByRole("option", { name: "deck (1)" }),
    ).toBeInTheDocument();
  });

  it("marca a baseline do conjunto no card", () => {
    setup({ baselines: { todos: "b1" } });
    renderAt();
    const [, mid, old] = sideItems();
    expect(within(old).getByText("Baseline")).toBeInTheDocument();
    expect(within(mid).queryByText("Baseline")).toBeNull();
  });

  it("o botão do dashboard chama toggleBaseline", () => {
    const toggle = setup();
    renderAt("/historico/b2");
    fireEvent.click(screen.getByRole("button", { name: "★ Definir como baseline" }));
    expect(toggle).toHaveBeenCalledWith(MID);
  });

  it("recolhe e mostra de novo a lista", () => {
    setup();
    renderAt();
    fireEvent.click(screen.getByRole("button", { name: "Recolher a lista de baterias" }));
    expect(within(screen.getByRole("complementary")).queryAllByRole("listitem")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Mostrar a lista de baterias" }));
    expect(sideItems()).toHaveLength(3);
  });

  it("abrir /historico/<id> seleciona aquela bateria", () => {
    setup();
    renderAt("/historico/b1");
    const selected = sideItems().filter((c) => c.getAttribute("aria-current") === "true");
    expect(selected.map((c) => c.getAttribute("data-batch-id"))).toEqual(["b1"]);
    expect(screen.getByRole("region", { name: "Dashboard da bateria" })).toHaveTextContent("b1");
  });

  it("sem parâmetro seleciona a mais recente e clicar no card navega", async () => {
    setup();
    renderAt();
    expect(screen.getByRole("region", { name: "Dashboard da bateria" })).toHaveTextContent("b3");
    fireEvent.click(within(sideItems()[2]).getByRole("link"));
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
