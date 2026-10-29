import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { agentStats, makeAgentLoadRun, makeLoadRun, stats } from "../fixtures";
import { LoadPerToolChart, perToolRows } from "./LoadPerToolChart";

describe("perToolRows", () => {
  it("modo tools: uma linha por tool com p95 e erros somados aos timeouts", () => {
    const run = makeLoadRun({
      per_tool: {
        deck_list: stats({ calls: 40, p95_ms: 70, errors: 2, timeouts: 1 }),
        docs_search: stats({ calls: 60, p95_ms: null }),
      },
    });
    expect(perToolRows(run)).toEqual([
      { name: "deck_list", p95_ms: 70, failed: 3 },
      { name: "docs_search", p95_ms: null, failed: 0 },
    ]);
  });

  it("modo agent: uma linha por caso", () => {
    const run = makeAgentLoadRun({
      per_case: {
        q1: { ...agentStats({ p95_ms: 20000, errors: 1, timeouts: 2 }), group: "g" },
      },
    });
    expect(perToolRows(run)).toEqual([{ name: "q1", p95_ms: 20000, failed: 3 }]);
  });
});

describe("LoadPerToolChart", () => {
  it("mostra o título por tool no modo tools", () => {
    render(<LoadPerToolChart run={makeLoadRun()} />);
    expect(screen.getByText("p95 e erros por tool")).toBeInTheDocument();
  });

  it("mostra o título por caso no modo agent", () => {
    render(<LoadPerToolChart run={makeAgentLoadRun()} />);
    expect(screen.getByText("p95 e erros por caso")).toBeInTheDocument();
  });

  it("sem chamadas mostra o aviso em vez do gráfico", () => {
    const run = makeLoadRun({ per_tool: { deck_list: stats({ calls: 0, ok: 0, p95_ms: null }) } });
    render(<LoadPerToolChart run={run} />);
    expect(screen.getByText("Sem chamadas")).toBeInTheDocument();
  });
});
