import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DECISAO_GO, SHA_A, SHA_B, manifesto, registro, rodada } from "@/data/fixtures.testutil";
import type { Rodada } from "@/data/rodada";
import { History } from "@/features/History";

function servir(r: Rodada) {
  const resumo = { ...r, manifesto: undefined, registros: undefined };
  const fetchMock = vi.fn(async (url: string) => {
    const corpo = url.endsWith("api/rodadas") ? { rodadas: [resumo] } : r;
    return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function abrir() {
  return render(
    <MemoryRouter initialEntries={["/historico"]}>
      <Routes>
        <Route path="/historico" element={<History />} />
        <Route path="/historico/:rodadaId" element={<History />} />
      </Routes>
    </MemoryRouter>,
  );
}

const M = (acerto: boolean, nota: number, interrupcoes: number, t: number, tokens: number | null) => ({
  acerto_tool: acerto,
  nota_juiz: nota,
  contornos: 0,
  interrupcoes,
  indice_autonomia: 0.5,
  t_total: t,
  tokens_entrada: tokens,
});

const REGISTROS = [
  registro({ config: "sem-mcp", caso: "caso-a", metricas: M(false, 1, 4, 20, 100), motivo: "juiz: ruim" }),
  registro({
    config: "mcp-1.0",
    caso: "caso-a",
    metricas: M(true, 2, 0, 12.345, 2000),
    motivo: "juiz: ótimo, veja /home/pessoa/dados/caso e C:\\Users\\pessoa\\x",
  }),
  registro({ config: "mcp-1.1", caso: "caso-a", metricas: M(true, 2, 0, 11, null) }),
  registro({ conjunto: "tools", agente: "claude", caso: "ferramenta-a", tools: [{ nome: "tool_a", ok: true, duracao_s: 1 }] }),
  registro({ conjunto: "deterministica", agente: "nenhum", config: "checkout", caso: "unitario-a" }),
];

afterEach(() => vi.unstubAllGlobals());

describe("Histórico das rodadas", () => {
  it("mostra as configuracoes lado a lado no formato da v19", async () => {
    servir(rodada("r1", REGISTROS));
    abrir();
    const resumo = await screen.findByRole("table", { name: "claude: resumo" });
    const cabecalho = within(resumo).getAllByRole("columnheader").map((c) => c.textContent);
    expect(cabecalho).toEqual([
      "condição",
      "n",
      "uso da tool esperada (0–1)",
      "nota juiz (0–2)",
      "contornos",
      "interrupções",
      "autonomia",
      "tempo (s)",
      "tokens entrada",
    ]);
    const linhas = within(resumo).getAllByRole("row").slice(1);
    expect(linhas.map((l) => within(l).getAllByRole("cell").map((c) => c.textContent))).toEqual([
      ["sem-mcp", "1", "0.00", "1.00", "0.00", "4.00", "0.50", "20.00", "100"],
      ["mcp-1.0", "1", "1.00", "2.00", "0.00", "0.00", "0.50", "12.35", "2000"],
      ["mcp-1.1", "1", "1.00", "2.00", "0.00", "0.00", "0.50", "11.00", "—"],
    ]);
    const cenarios = screen.getByRole("table", { name: "claude: por cenário" });
    expect(within(cenarios).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "cenário",
      "sem-mcp",
      "mcp-1.0",
      "mcp-1.1",
    ]);
    expect(within(cenarios).getByText("1.00 / 2.00 / 0.00 / 12.35")).toBeInTheDocument();
  });

  it("mostra sha256 e origem de cada wheel", async () => {
    servir(rodada("r1", REGISTROS));
    abrir();
    const tabela = await screen.findByRole("table", { name: "Wheels por configuração" });
    expect(within(tabela).getByText(SHA_A)).toBeInTheDocument();
    expect(within(tabela).getByText(SHA_B)).toBeInTheDocument();
    expect(within(tabela).getByText("registro-publico")).toBeInTheDocument();
    expect(within(tabela).getByText("build-local")).toBeInTheDocument();
    expect(within(tabela).getByText("1.0.0")).toBeInTheDocument();
    const imagens = screen.getByRole("table", { name: "Imagens" });
    expect(within(imagens).getByText("bateria-claude:1")).toBeInTheDocument();
    expect(within(imagens).getAllByText("3.0.0").length).toBeGreaterThan(0);
  });

  it("mostra no topo o veredito do go-no-go, os bloqueios e a evidência", async () => {
    const r = rodada("r1", REGISTROS, {
      go_no_go: {
        ...DECISAO_GO,
        veredito: "no-go",
        bloqueios: [
          {
            regra: "regressao_tool",
            conjunto: "tools",
            caso: "ferramenta-a",
            agente: "claude",
            evidencia: ["tools/ferramenta-a/claude/mcp-1.1/1"],
          },
        ],
      },
    });
    servir(r);
    abrir();
    const painel = await screen.findByRole("region", { name: "Veredito do go-no-go" });
    expect(within(painel).getByText("no-go")).toBeInTheDocument();
    expect(within(painel).getByText(/regressao_tool/)).toBeInTheDocument();
    expect(within(painel).getByText("tools/ferramenta-a/claude/mcp-1.1/1")).toBeInTheDocument();
    const topo = screen.getByLabelText("Dashboard da rodada").children;
    const ordem = [...topo].map((e) => e.getAttribute("aria-label"));
    expect(ordem.indexOf("Veredito do go-no-go")).toBeLessThan(ordem.indexOf("Configurações"));
  });

  it("avisa quando o go-no-go ainda não rodou", async () => {
    servir(rodada("r1", REGISTROS, { go_no_go: null }));
    abrir();
    expect(await screen.findByText("go-no-go ainda não rodado")).toBeInTheDocument();
  });

  it("filtra por conjunto: determinística, tools e usuário", async () => {
    servir(rodada("r1", REGISTROS));
    abrir();
    await screen.findByRole("table", { name: "claude: resumo" });
    const filtro = screen.getByLabelText("Conjunto");
    expect(within(filtro).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "determinística",
      "tools",
      "usuário",
    ]);
    fireEvent.change(filtro, { target: { value: "tools" } });
    expect(await screen.findByText("tool_a")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "claude: resumo" })).not.toBeInTheDocument();
    fireEvent.change(filtro, { target: { value: "deterministica" } });
    expect(await screen.findByText("unitario-a")).toBeInTheDocument();
    expect(screen.queryByText("tool_a")).not.toBeInTheDocument();
  });

  it("mostra a nota e a justificativa do juiz sem o prefixo", async () => {
    servir(rodada("r1", REGISTROS));
    abrir();
    const painel = await screen.findByRole("region", { name: "Notas e justificativas do juiz" });
    expect(within(painel).getByText("ruim")).toBeInTheDocument();
    expect(within(painel).queryByText(/^juiz:/)).not.toBeInTheDocument();
  });

  it("não mostra caminho de máquina nem o da pasta de resultados", async () => {
    const r = rodada("r1", REGISTROS, {
      erro: "falha em /var/dados/resultados/r1/manifesto.json",
      manifesto: manifesto({
        wheels: {
          "mcp-1.0": { arquivo: "a.whl", sha256: SHA_A, origem: "/home/pessoa/build/a.whl" },
          "mcp-1.1": { arquivo: "b.whl", sha256: SHA_B, origem: "C:\\Users\\pessoa\\b.whl" },
        },
      }),
    });
    servir(r);
    abrir();
    await screen.findByRole("region", { name: "Notas e justificativas do juiz" });
    await waitFor(() => expect(screen.getAllByText("<caminho>").length).toBeGreaterThan(0));
    const texto = document.body.textContent ?? "";
    expect(texto).not.toContain("/home/");
    expect(texto).not.toContain("C:\\");
    expect(texto).not.toContain("/var/dados/resultados");
  });
});
