import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RunResultItem } from "@/services/launcherApi";
import { CaseDetail, type CaseSummary } from "./CaseDetail";

const CASE: CaseSummary = {
  id: "docs-list-all",
  query: "Liste todas as páginas da documentação",
  expected: "docs_list",
  tags: ["docs"],
  timeoutS: 300,
};

const RESULT: RunResultItem = {
  test_id: "docs-list-all",
  query: CASE.query,
  expected_tool: "docs_list",
  expected_tools: null,
  actual_tool: "docs_list",
  all_tool_calls: [
    { name: "docs_list", args: { __tool_use_purpose: "Listar as páginas" }, tool_id: "t1" },
  ],
  status: "pass",
  latency_ms: 69635,
  tool_latency_ms: null,
  mcp_used: true,
  correct_tool: true,
  correct_result: true,
  agent_response: "A documentação tem 65 páginas",
  error_message: null,
  tags: ["docs"],
  validation_checks: [{ name: "uses_mcp", passed: true, message: "MCP usado: docs_list" }],
};

function renderDetail(result: RunResultItem | null) {
  render(
    <CaseDetail caseMeta={CASE} result={result} running={false} canRun onRun={vi.fn()} />,
  );
}

describe("CaseDetail", () => {
  it("não quebra com o resumo de um launcher antigo", () => {
    const summary = {
      test_id: "docs-list-all",
      status: "pass",
      expected_tool: "docs_list",
      actual_tool: "docs_list",
      mcp_used: true,
      correct_tool: true,
      correct_result: true,
      latency_ms: 1200,
      error_message: null,
      response_preview: "trecho da resposta",
    } as unknown as RunResultItem;
    renderDetail(summary);
    expect(screen.getByText("trecho da resposta")).toBeInTheDocument();
    expect(screen.queryByText(/Tools chamadas/)).toBeNull();
  });

  it("antes de rodar mostra a tool esperada, o timeout e o aviso", () => {
    renderDetail(null);
    expect(screen.getByRole("heading", { name: CASE.query })).toBeInTheDocument();
    expect(screen.getByText("5 min")).toBeInTheDocument();
    expect(screen.getByText(/ainda não rodou/)).toBeInTheDocument();
  });

  it("depois de rodar mostra o mesmo detalhe do Histórico, com o timeout do caso", () => {
    renderDetail(RESULT);
    expect(screen.getByText("Listar as páginas")).toBeInTheDocument();
    expect(screen.getByText("MCP usado: docs_list")).toBeInTheDocument();
    expect(screen.getByText("A documentação tem 65 páginas")).toBeInTheDocument();
    expect(screen.getByText("69635 ms")).toBeInTheDocument();
    expect(screen.getByText("5 min")).toBeInTheDocument();
  });

  it("a resposta do agente vem em markdown, sem HTML cru", () => {
    renderDetail({
      ...RESULT,
      agent_response: "## Páginas\n\n- **math/sddp**\n- `overview`\n\n<script>alert(1)</script>",
    });
    expect(screen.getByRole("heading", { name: "Páginas" })).toBeInTheDocument();
    expect(screen.getByText("math/sddp").tagName).toBe("STRONG");
    expect(screen.getByText("overview").tagName).toBe("CODE");
    expect(document.querySelector(".nm-markdown script")).toBeNull();
  });

  it("cada tool chamada com argumentos abre e fecha; sem argumentos, é só a linha", () => {
    renderDetail({
      ...RESULT,
      all_tool_calls: [
        { name: "docs_list", args: { __tool_use_purpose: "Listar" }, tool_id: "t1" },
        {
          name: "docs_read",
          args: { __tool_use_purpose: "Ler a página", page: "math/sddp" },
          tool_id: "t2",
        },
      ],
    });
    const withArgs = screen.getByText("Ler a página").closest("details");
    expect(withArgs).not.toBeNull();
    expect(withArgs).not.toHaveAttribute("open");
    expect(withArgs).toHaveTextContent('"page": "math/sddp"');
    expect(screen.getByText("Listar").closest("details")).toBeNull();
  });
});
