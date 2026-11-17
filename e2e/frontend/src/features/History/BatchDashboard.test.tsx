import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CAMINHO_POSIX, loteSintetico } from "@/data/fixtures.testutil";
import { TestDetail } from "@/shared/components/TestDetail";
import { BatchOverview } from "./components/BatchCards";
import { BatchCharts } from "./charts/BatchCharts";
import { BatchDashboard } from "./components/BatchDashboard";

const REF = loteSintetico("ref", "2026-01-01T10:00:00Z", [
  { caso: "q1", tools: [["case_summary", 0.3]], duracao_s: 1.2 },
  { caso: "q2", tools: [["case_summary", 0.3]], duracao_s: 1.2 },
  { caso: "q3", estado: "falhou", tools: [["case_summary", 0.3]], duracao_s: 1.2 },
]);
const CUR = loteSintetico("cur", "2026-01-02T10:00:00Z", [
  { caso: "q1", estado: "falhou", tools: [["case_summary", 0.3]], duracao_s: 1.2 },
  { caso: "q2", tools: [["case_summary", 0.3]], duracao_s: 1.2 },
  { caso: "q3", tools: [["case_summary", 0.3]], duracao_s: 1.2 },
]);
const ALONE = loteSintetico(
  "alone",
  "2026-01-03T10:00:00Z",
  [{ caso: "q1", tools: [["case_summary", 0.3]], duracao_s: 1.2 }],
  "mcp-2.0",
);

function setup(over: Partial<React.ComponentProps<typeof BatchDashboard>> = {}) {
  render(<BatchDashboard batch={CUR} all={[CUR, REF, ALONE]} {...over} />);
}

describe("BatchHeader", () => {
  it("mostra configuração e agente, versão do MCP e commit curto", () => {
    setup();
    expect(screen.getByRole("heading", { name: /^mcp-1\.0 · claude — / })).toBeInTheDocument();
    expect(screen.getByText("v1.0.0")).toBeInTheDocument();
    expect(screen.getByText("abc1234")).toBeInTheDocument();
  });

  it("omite a versão quando é unknown", () => {
    setup({ batch: { ...CUR, mcp_version: "unknown" } });
    expect(screen.queryByText(/vunknown/)).toBeNull();
  });

  it("não oferece baseline", () => {
    setup();
    expect(screen.queryByRole("button", { name: /baseline/i })).toBeNull();
  });

  it("Baixar resumo fica habilitado por padrão e usa o handler quando há", () => {
    const { unmount } = render(<BatchDashboard batch={CUR} all={[CUR]} />);
    expect(screen.getByRole("button", { name: "⤓ Baixar resumo" })).toBeEnabled();
    unmount();
    const onDownloadSummary = vi.fn();
    render(<BatchDashboard batch={CUR} all={[CUR]} onDownloadSummary={onDownloadSummary} />);
    fireEvent.click(screen.getByRole("button", { name: "⤓ Baixar resumo" }));
    expect(onDownloadSummary).toHaveBeenCalled();
  });

  it("diz o que o registro não guarda", () => {
    setup({ avisos: ["O registro não guarda a resposta do agente."] });
    expect(screen.getByRole("note")).toHaveTextContent("não guarda a resposta");
  });
});

describe("ChangesStrip", () => {
  it("lista as perguntas que passaram a falhar e a passar", () => {
    setup();
    const strip = screen.getByRole("region", {
      name: "Mudanças contra a referência",
    });
    expect(strip).toHaveTextContent("1 pergunta passou a falhar");
    expect(strip).toHaveTextContent("1 passou a passar");
    expect(
      within(strip).getByRole("button", { name: "q1" }),
    ).toBeInTheDocument();
    expect(
      within(strip).getByRole("button", { name: "q3" }),
    ).toBeInTheDocument();
  });

  it("some sem referência", () => {
    setup({ batch: ALONE });
    expect(
      screen.queryByRole("region", { name: "Mudanças contra a referência" }),
    ).toBeNull();
  });

  it("clicar num id abre o detalhe da pergunta", () => {
    setup();
    expect(screen.queryByText("não gravada no registro")).toBeNull();
    const strip = screen.getByRole("region", {
      name: "Mudanças contra a referência",
    });
    fireEvent.click(within(strip).getByRole("button", { name: "q1" }));
    expect(screen.getAllByText("case_summary").length).toBeGreaterThan(0);
    expect(screen.getByText("não gravada no registro")).toBeInTheDocument();
  });
});

describe("BatchOverview e BatchStats", () => {
  it("mostra a aprovação, o Δ e as latências", () => {
    setup();
    expect(screen.getByText("66,7%")).toBeInTheDocument();
    expect(screen.getByText("0,0 pp")).toBeInTheDocument();
    expect(screen.getAllByText("1200 ms").length).toBeGreaterThan(0);
  });

  it("mostra — no Δ sem referência", () => {
    render(<BatchOverview batch={ALONE} reference={null} />);
    expect(screen.getByLabelText("Δ vs referência")).toHaveTextContent("—");
  });
});

describe("QuestionList", () => {
  it("marca a mudança de cada pergunta", () => {
    setup();
    const list = screen.getByRole("region", { name: "Perguntas" });
    expect(within(list).getByText("✗ passou a falhar")).toBeInTheDocument();
    expect(within(list).getByText("✓ passou a passar")).toBeInTheDocument();
  });

  it("filtra por status", () => {
    setup();
    const list = screen.getByRole("region", { name: "Perguntas" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    fireEvent.change(within(list).getByLabelText("Status"), {
      target: { value: "fail" },
    });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("q1");
  });

  it("o detalhe mostra as tools chamadas, o tempo na tool e o motivo, sem caminho", () => {
    const lote = loteSintetico("m", "2026-01-04T10:00:00Z", [
      {
        caso: "q9",
        estado: "falhou",
        tools: [["case_summary", 0.3]],
        motivo: `não achou ${CAMINHO_POSIX}/Meus Documentos/x.json`,
      },
    ]);
    render(<BatchDashboard batch={lote} all={[lote]} />);
    const list = screen.getByRole("region", { name: "Perguntas" });
    fireEvent.click(within(list).getByRole("button", { name: /q9/ }));
    expect(screen.getByText("300 ms")).toBeInTheDocument();
    expect(screen.getByText("não achou <caminho>")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(CAMINHO_POSIX);
  });

  it("filtra pelo grupo da primeira tool chamada", () => {
    const lote = loteSintetico("g", "2026-01-04T10:00:00Z", [
      { caso: "q1", tools: [["docs_list", 0.1]] },
      { caso: "q2", tools: [["deck_list", 0.1]] },
    ]);
    render(<BatchDashboard batch={lote} all={[lote]} />);
    const list = screen.getByRole("region", { name: "Perguntas" });
    fireEvent.change(within(list).getByLabelText("Grupo"), { target: { value: "deck" } });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText("q2", { selector: "code" })).toBeInTheDocument();
  });

  it("o propósito da chamada vira texto e as checagens viram lista", () => {
    const tr = {
      ...CUR.test_results[1],
      all_tool_calls: [
        { name: "docs_list", args: { __tool_use_purpose: "Listar as páginas" }, tool_id: "t1" },
      ],
      validation_checks: [
        { name: "uses_mcp", passed: true, message: "MCP usado: docs_list" },
        { name: "correct_result", passed: false, message: "Resultado sem as páginas" },
      ],
    };
    render(<TestDetail tr={tr} expected="docs_list" />);
    expect(screen.getByText("Listar as páginas")).toBeInTheDocument();
    expect(screen.queryByText(/__tool_use_purpose/)).toBeNull();
    expect(screen.getByText("MCP usado: docs_list")).toBeInTheDocument();
    expect(screen.getByText("✗ falhou")).toHaveAttribute("data-status", "fail");
  });
});

describe("ConjuntoEvolution", () => {
  it("aparece com mais de uma bateria do conjunto", () => {
    setup();
    expect(
      screen.getByRole("region", { name: "Evolução do conjunto" }),
    ).toBeInTheDocument();
  });

  it("avisa na tela quando só há uma rodada da configuração", () => {
    setup({ batch: ALONE, all: [ALONE] });
    expect(screen.getByRole("region", { name: "Evolução do conjunto" })).toHaveTextContent(
      "pede mais de uma rodada",
    );
  });

  it("vem logo depois do resumo da bateria", () => {
    setup();
    const overview = screen.getByRole("region", { name: "Resumo da bateria" });
    expect(overview.nextElementSibling).toBe(
      screen.getByRole("region", { name: "Evolução do conjunto" }),
    );
  });
});

describe("BatchCharts", () => {
  it("os gráficos de uma barra por item ocupam a linha toda; os menores vêm em pares", () => {
    const batch = loteSintetico("charts", "2026-01-04T10:00:00Z", [
      { caso: "q1", tools: [["case_summary", 0.1]] },
      { caso: "q2", estado: "falhou", tools: [["docs_list", 0.1]] },
    ]);
    render(<BatchCharts batch={batch} />);
    const cards = screen.getAllByRole("figure");
    expect(cards.map((c) => within(c).getByRole("heading").textContent)).toEqual([
      "Status",
      "Tools por pergunta",
      "Tempo por pergunta",
      "Tools mais usadas",
      "Aprovação por grupo",
      "Funil de diagnóstico",
    ]);
    expect(cards.filter((c) => c.dataset.wide === "true").length).toBe(2);
    expect(cards[2]).toHaveAttribute("data-wide", "true");
    expect(cards[3]).toHaveAttribute("data-wide", "true");
  });
});
