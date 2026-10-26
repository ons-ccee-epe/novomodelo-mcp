import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { makeBatch } from "@/shared/fixtures.testutil";
import type { BatchResult, TestResult } from "@/shared/types";
import { BatchCards } from "./components/BatchCards";
import { BatchDashboard } from "./components/BatchDashboard";

function detailed(b: BatchResult): BatchResult {
  const test_results = b.test_results.map(
    (r) =>
      ({
        ...r,
        query: `pergunta do ${r.test_id}`,
        actual_tool: "case_summary",
        all_tool_calls: [{ name: "case_summary", args: { path: "caso/x", depth: 2 } }],
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
    metrics: { avg_latency_ms: 1234, p95_latency_ms: 2500 } as BatchResult["metrics"],
  };
}

const REF = detailed(
  makeBatch("ref", [["q1", "pass", "case_summary"], ["q2", "pass", "case_summary"], ["q3", "fail", "case_summary"]], {
    timestamp: "2026-01-01T10:00:00",
    conjunto: "todos",
  }),
);
const CUR = detailed(
  makeBatch("cur", [["q1", "fail", "case_summary"], ["q2", "pass", "case_summary"], ["q3", "pass", "case_summary"]], {
    timestamp: "2026-01-02T10:00:00",
    conjunto: "todos",
  }),
);
const ALONE = detailed(
  makeBatch("alone", [["q1", "pass", "case_summary"]], {
    timestamp: "2026-01-03T10:00:00",
    conjunto: "grupo:deck",
  }),
);

function setup(over: Partial<React.ComponentProps<typeof BatchDashboard>> = {}) {
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
    expect(screen.getByText("Esteira completa")).toBeInTheDocument();
    expect(screen.getByText(/1\.2\.3/)).toBeInTheDocument();
    expect(screen.getByText("abcdef0")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "★ Definir como baseline" }));
    expect(toggle).toHaveBeenCalledWith(CUR);
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
    expect(screen.getByRole("button", { name: "Remover baseline" })).toBeInTheDocument();
  });

  it("mostra a recusa do launcher", async () => {
    setup({
      onToggleBaseline: vi.fn(async () => {
        throw new Error("launcher recusou");
      }),
    });
    fireEvent.click(screen.getByRole("button", { name: "★ Definir como baseline" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("launcher recusou");
  });

  it("Baixar resumo fica habilitado por padrão e usa o handler quando há", () => {
    const { unmount } = render(
      <BatchDashboard batch={CUR} all={[CUR]} baselines={{}} launcherOnline onToggleBaseline={vi.fn()} />,
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
    const strip = screen.getByRole("region", { name: "Mudanças contra a referência" });
    expect(strip).toHaveTextContent("1 pergunta passou a falhar");
    expect(strip).toHaveTextContent("1 passou a passar");
    expect(within(strip).getByRole("button", { name: "q1" })).toBeInTheDocument();
    expect(within(strip).getByRole("button", { name: "q3" })).toBeInTheDocument();
  });

  it("some sem referência", () => {
    setup({ batch: ALONE });
    expect(screen.queryByRole("region", { name: "Mudanças contra a referência" })).toBeNull();
  });

  it("clicar num id abre o detalhe da pergunta", () => {
    setup();
    expect(screen.queryByText("resposta do q1")).toBeNull();
    const strip = screen.getByRole("region", { name: "Mudanças contra a referência" });
    fireEvent.click(within(strip).getByRole("button", { name: "q1" }));
    expect(screen.getByText("pergunta do q1", { selector: "pre" })).toBeInTheDocument();
  });
});

describe("BatchCards", () => {
  it("mostra a aprovação, o Δ e as latências", () => {
    setup();
    expect(screen.getByText("66,7%")).toBeInTheDocument();
    expect(screen.getByText("▲ +0,0 pp")).toBeInTheDocument();
    expect(screen.getByText("1234 ms")).toBeInTheDocument();
    expect(screen.getByText("2500 ms")).toBeInTheDocument();
  });

  it("mostra — no Δ sem referência", () => {
    render(<BatchCards batch={ALONE} reference={null} />);
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
    fireEvent.change(within(list).getByLabelText("Status"), { target: { value: "fail" } });
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
});

describe("ConjuntoEvolution", () => {
  it("existe como seção da bateria", () => {
    setup();
    expect(screen.getByRole("region", { name: "Evolução do conjunto" })).toBeInTheDocument();
  });
});
