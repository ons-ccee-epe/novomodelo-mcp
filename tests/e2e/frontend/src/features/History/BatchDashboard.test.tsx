import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeBatch } from "@/shared/fixtures.testutil";
import type { BatchResult, TestResult } from "@/shared/types";
import { BatchOverview } from "./components/BatchCards";
import { TestDetail } from "@/shared/components/TestDetail";
import { BatchCharts } from "./charts/BatchCharts";
import { BatchDashboard } from "./components/BatchDashboard";

function detailed(b: BatchResult): BatchResult {
  const test_results = b.test_results.map(
    (r) =>
      ({
        ...r,
        query: `pergunta do ${r.test_id}`,
        actual_tool: "case_summary",
        all_tool_calls: [
          { name: "case_summary", args: { path: "caso/x", depth: 2 } },
        ],
        latency_ms: 1200,
        tool_latency_ms: 300,
        agent_response: `resposta do ${r.test_id}`,
        error_message: null,
        tags: [],
        validation_checks: [],
      }) as TestResult,
  );
  const passed = test_results.filter((r) => r.status === "pass").length;
  return {
    ...b,
    test_results,
    total_tests: test_results.length,
    passed,
    cobre_mcp_version: "1.2.3",
    git_commit_sha: "abcdef0123456789",
    metrics: {
      avg_latency_ms: 1234,
      p95_latency_ms: 2500,
    } as BatchResult["metrics"],
  };
}

const REF = detailed(
  makeBatch(
    "ref",
    [
      ["q1", "pass", "case_summary"],
      ["q2", "pass", "case_summary"],
      ["q3", "fail", "case_summary"],
    ],
    {
      timestamp: "2026-01-01T10:00:00",
      conjunto: "todos",
    },
  ),
);
const CUR = detailed(
  makeBatch(
    "cur",
    [
      ["q1", "fail", "case_summary"],
      ["q2", "pass", "case_summary"],
      ["q3", "pass", "case_summary"],
    ],
    {
      timestamp: "2026-01-02T10:00:00",
      conjunto: "todos",
    },
  ),
);
const ALONE = detailed(
  makeBatch("alone", [["q1", "pass", "case_summary"]], {
    timestamp: "2026-01-03T10:00:00",
    conjunto: "grupo:deck",
  }),
);

function setup(
  over: Partial<React.ComponentProps<typeof BatchDashboard>> = {},
) {
  const onToggleBaseline = vi.fn(async () => {});
  render(
    <BatchDashboard
      batch={CUR}
      all={[CUR, REF, ALONE]}
      baselines={{}}
      launcherOnline
      onToggleBaseline={onToggleBaseline}
      {...over}
    />,
  );
  return onToggleBaseline;
}

describe("BatchHeader", () => {
  it("mostra conjunto, versão, commit curto e o botão de baseline", () => {
    const toggle = setup();
    expect(screen.getByRole("heading", { name: /^Esteira completa — / })).toBeInTheDocument();
    expect(screen.getByText("Esteira")).toHaveAttribute("title", "Esteira completa");
    expect(screen.getByText(/1\.2\.3/)).toBeInTheDocument();
    expect(screen.getByText("abcdef0")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "★ Definir como baseline" }),
    );
    expect(toggle).toHaveBeenCalledWith(CUR);
  });

  it("omite a versão quando é unknown", () => {
    setup({ batch: { ...CUR, cobre_mcp_version: "unknown" } });
    expect(screen.queryByText(/vunknown/)).toBeNull();
  });

  it("offline o botão de baseline fica desabilitado", () => {
    const toggle = setup({ launcherOnline: false });
    const btn = screen.getByRole("button", { name: "★ Definir como baseline" });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(toggle).not.toHaveBeenCalled();
  });

  it("oferece Remover baseline quando a bateria já é a baseline", () => {
    setup({ baselines: { todos: "cur" } });
    expect(
      screen.getByRole("button", { name: "Remover baseline" }),
    ).toBeInTheDocument();
  });

  it("mostra a recusa do launcher", async () => {
    setup({
      onToggleBaseline: vi.fn(async () => {
        throw new Error("launcher recusou");
      }),
    });
    fireEvent.click(
      screen.getByRole("button", { name: "★ Definir como baseline" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "launcher recusou",
    );
  });

  it("Baixar resumo fica habilitado por padrão e usa o handler quando há", () => {
    const { unmount } = render(
      <BatchDashboard
        batch={CUR}
        all={[CUR]}
        baselines={{}}
        launcherOnline
        onToggleBaseline={vi.fn()}
      />,
    );
    const off = screen.getByRole("button", { name: "⤓ Baixar resumo" });
    expect(off).toBeEnabled();
    unmount();
    const onDownloadSummary = vi.fn();
    render(
      <BatchDashboard
        batch={CUR}
        all={[CUR]}
        baselines={{}}
        launcherOnline
        onToggleBaseline={vi.fn()}
        onDownloadSummary={onDownloadSummary}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "⤓ Baixar resumo" }));
    expect(onDownloadSummary).toHaveBeenCalled();
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
    expect(screen.queryByText("resposta do q1")).toBeNull();
    const strip = screen.getByRole("region", {
      name: "Mudanças contra a referência",
    });
    fireEvent.click(within(strip).getByRole("button", { name: "q1" }));
    expect(screen.getByText("resposta do q1")).toBeInTheDocument();
  });
});

describe("BatchOverview e BatchStats", () => {
  it("mostra a aprovação, o Δ e as latências", () => {
    setup();
    expect(screen.getByText("66,7%")).toBeInTheDocument();
    expect(screen.getByText("0,0 pp")).toBeInTheDocument();
    expect(screen.getByText("1234 ms")).toBeInTheDocument();
    expect(screen.getByText("2500 ms")).toBeInTheDocument();
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

  it("o detalhe mostra os argumentos da tool call em JSON", () => {
    setup();
    const list = screen.getByRole("region", { name: "Perguntas" });
    fireEvent.click(within(list).getByRole("button", { name: /q2/ }));
    expect(screen.getByText(/"path": "caso\/x"/)).toBeInTheDocument();
    expect(screen.getByText("resposta do q2")).toBeInTheDocument();
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

  it("some quando o conjunto tem uma bateria só", () => {
    setup({ batch: ALONE });
    expect(
      screen.queryByRole("region", { name: "Evolução do conjunto" }),
    ).toBeNull();
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
    const batch = makeBatch("charts", [
      ["q1", "pass", "case_summary"],
      ["q2", "fail", "docs_list"],
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
