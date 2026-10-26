import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Functional } from "./index";

const CASES = [
  { id: "q_deck", query: "lista decks", expected_tool: "deck_list", expected_tools: null, tags: [], timeout_s: null, requires: [] },
  { id: "q_docs", query: "busca docs", expected_tool: "docs_search", expected_tools: null, tags: [], timeout_s: null, requires: [] },
];

function stub(online: boolean) {
  const mock = vi.fn(async (url: string) => {
    const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;
    if (!online) return { ok: false, status: 503, json: async () => ({}) } as Response;
    if (url === "api/health") return ok({});
    if (url === "api/providers") {
      return ok({ providers: [{ id: "claude", label: "Claude", binary: "claude", installed: true }], default: "claude" });
    }
    if (url === "api/cases") return ok({ cases: CASES });
    if (url.startsWith("api/command-preview")) {
      return ok({ conjunto: "todos", total: 2, terminal: "cmd-terminal", terminal_note: null, agent: "cmd-agente" });
    }
    return { ok: false, status: 404, json: async () => ({}) } as Response;
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

function previewUrls(mock: ReturnType<typeof stub>): string[] {
  return mock.mock.calls.map(([u]) => u as string).filter((u) => u.startsWith("api/command-preview"));
}

function renderIt() {
  return render(
    <MemoryRouter>
      <Functional />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Functional", () => {
  it("mostra o preview da esteira completa sem filtros", async () => {
    const mock = stub(true);
    renderIt();
    expect(await screen.findByText("cmd-terminal")).toBeInTheDocument();
    expect(previewUrls(mock).at(-1)).toBe("api/command-preview?provider=claude");
  });

  it("escolher um grupo atualiza o preview com tags", async () => {
    const mock = stub(true);
    renderIt();
    await screen.findByText("cmd-terminal");

    fireEvent.click(screen.getByRole("button", { name: /^deck \(1\)/ }));

    await waitFor(() =>
      expect(previewUrls(mock).at(-1)).toBe("api/command-preview?provider=claude&tags=deck"),
    );
  });

  it("escolher uma pergunta atualiza o preview com case_id", async () => {
    const mock = stub(true);
    renderIt();
    await screen.findByText("cmd-terminal");

    fireEvent.click(screen.getByRole("button", { name: /q_docs/ }));

    await waitFor(() =>
      expect(previewUrls(mock).at(-1)).toBe("api/command-preview?provider=claude&case_id=q_docs"),
    );
  });

  it("com o launcher offline não mostra o comando equivalente", async () => {
    const mock = stub(false);
    renderIt();
    expect(await screen.findByText(/Launcher de testes offline/)).toBeInTheDocument();
    expect(screen.queryByText("Bateria pelo terminal")).not.toBeInTheDocument();
    expect(previewUrls(mock)).toHaveLength(0);
  });
});
