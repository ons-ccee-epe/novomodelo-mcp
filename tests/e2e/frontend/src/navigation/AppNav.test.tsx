import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "@/navigation";
import { carregarRodadas } from "@/data/rodada";

vi.mock("@/data/rodada", () => ({
  carregarRodadas: vi.fn(),
  carregarRodada: vi.fn().mockRejectedValue(new Error("sem rodada")),
}));
vi.mock("@/services/launcherApi", () => ({
  launcherHealthy: vi.fn().mockResolvedValue(true),
}));
vi.mock("@/features/Functional", () => ({
  Functional: () => <div>tela funcional</div>,
}));
vi.mock("@/features/Load", () => ({
  Load: () => <div>tela carga</div>,
}));

const mockedIndex = vi.mocked(carregarRodadas);

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedIndex.mockReset();
  mockedIndex.mockResolvedValue([
    { rodada: "20261025_100000_abc", configs: ["sem-mcp", "mcp-1.2"] },
    { rodada: "20261024_100000_abc", configs: ["sem-mcp"] },
  ] as never);
});

describe("AppLayout", () => {
  it("mostra o título e as três abas", async () => {
    renderAt("/funcionais");
    expect(
      screen.getByRole("heading", { name: "Testes Automatizados · MCP NovoModelo" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Testes Funcionais" })).toHaveAttribute(
      "href",
      "/funcionais",
    );
    expect(screen.getByRole("link", { name: "Testes de Carga" })).toHaveAttribute("href", "/carga");
    expect(screen.getByRole("link", { name: "Histórico" })).toHaveAttribute("href", "/historico");
    await waitFor(() => expect(mockedIndex).toHaveBeenCalled());
  });

  it("mostra a última rodada, as configurações e o launcher na engrenagem", async () => {
    renderAt("/funcionais");
    await waitFor(() => expect(mockedIndex).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Informações do ambiente" }));
    expect(await screen.findByText("20261025_100000_abc")).toBeInTheDocument();
    expect(screen.getByText("sem-mcp, mcp-1.2")).toBeInTheDocument();
    expect(await screen.findByText("online")).toBeInTheDocument();
    expect(screen.getByText("stdio")).toBeInTheDocument();
  });

  it("alterna o modo noturno", () => {
    renderAt("/funcionais");
    const before = document.documentElement.dataset.theme;
    fireEvent.click(screen.getByRole("button", { name: /Usar modo (noturno|claro)/ }));
    expect(document.documentElement.dataset.theme).not.toBe(before);
  });

  it.each(["/", "/qualquer"])("%s cai em Testes Funcionais", async (path) => {
    renderAt(path);
    expect(await screen.findByText("tela funcional")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Testes Funcionais" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("marca a aba ativa", async () => {
    renderAt("/carga");
    expect(await screen.findByText("tela carga")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Testes de Carga" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Testes Funcionais" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("mantém Histórico ativa no detalhe de uma rodada", async () => {
    renderAt("/historico/20261024_100000_abc");
    expect(screen.getByRole("link", { name: "Histórico" })).toHaveAttribute("aria-current", "page");
    await waitFor(() => expect(mockedIndex).toHaveBeenCalled());
  });

  it("não mostra nada quando o index falha", async () => {
    mockedIndex.mockRejectedValue(new Error("falhou"));
    renderAt("/funcionais");
    await waitFor(() => expect(mockedIndex).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Informações do ambiente" }));
    expect(screen.queryByText(/^2026/)).not.toBeInTheDocument();
  });
});
