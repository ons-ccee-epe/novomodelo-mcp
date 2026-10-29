import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Functional } from "./index";

function stub() {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    const corpo = init?.method === "POST"
      ? { rodada: "r9", status: "em_andamento" }
      : { comando: "python -m tests.e2e rodar --mcp sem", argumentos: [] };
    return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("Disparo da rodada", () => {
  it("dispara por POST /api/rodadas só com os campos da lista branca", async () => {
    const fetchMock = stub();
    render(
      <MemoryRouter>
        <Functional />
      </MemoryRouter>,
    );
    fireEvent.change(screen.getByLabelText("Repetições"), { target: { value: "3" } });
    fireEvent.click(screen.getByLabelText("usuário"));
    fireEvent.click(screen.getByRole("button", { name: "Disparar rodada" }));
    await screen.findByRole("status");
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(post[0]).toBe("api/rodadas");
    expect(JSON.parse(post[1]!.body as string)).toEqual({
      mcp: ["sem"],
      conjuntos: ["usuario"],
      repeticoes: 3,
    });
    expect(screen.getByRole("link", { name: "Ver no Histórico" })).toHaveAttribute("href", "/historico/r9");
    const urls = fetchMock.mock.calls.map(([u]) => String(u));
    expect(urls.some((u) => /providers|\/runs/.test(u))).toBe(false);
  });

  it("mostra o motivo da recusa do launcher", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_u: string, init?: RequestInit) =>
        init?.method === "POST"
          ? ({ ok: false, status: 409, json: async () => ({ detail: "já há um run ativo" }) } as unknown as Response)
          : ({ ok: true, status: 200, json: async () => ({ comando: "x", argumentos: [] }) } as unknown as Response),
      ),
    );
    render(
      <MemoryRouter>
        <Functional />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Disparar rodada" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("já há um run ativo"));
  });
});
