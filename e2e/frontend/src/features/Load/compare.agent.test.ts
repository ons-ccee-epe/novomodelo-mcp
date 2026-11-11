import { describe, expect, it } from "vitest";

import {
  AGENT_COMPARED_METRICS,
  compareCaseP95,
  compareStats,
  configDifferences,
} from "./compare";
import { agentStats, makeAgentLoadRun, makeLoadRun } from "./fixtures";

describe("compareStats no modo agente", () => {
  it("compara casos/min, aprovação e latência", () => {
    const deltas = compareStats(
      agentStats({ throughput_cpm: 2, pass_rate: 0.9, error_rate: 0.1, p95_ms: 18000 }),
      agentStats({ throughput_cpm: 1, pass_rate: 0.7, error_rate: 0.1, p95_ms: 20000 }),
      AGENT_COMPARED_METRICS,
    );
    const byKey = Object.fromEntries(deltas.map((d) => [d.spec.key, d]));
    expect(byKey.throughput_cpm).toMatchObject({ delta: 1, trend: "better" });
    expect(byKey.pass_rate.trend).toBe("better");
    expect(byKey.error_rate.trend).toBe("flat");
    expect(byKey.p95_ms.trend).toBe("better");
  });
});

describe("compareCaseP95", () => {
  it("compara só os casos presentes nas duas cargas", () => {
    const current = makeAgentLoadRun({
      per_case: {
        a: { ...agentStats({ p95_ms: 100 }), group: "docs" },
        nova: { ...agentStats(), group: "docs" },
      },
    });
    const previous = makeAgentLoadRun({ per_case: { a: { ...agentStats({ p95_ms: 80 }), group: "docs" } } });
    expect(compareCaseP95(current, previous)).toEqual([
      { tool: "a", current: 100, previous: 80, delta: 20, trend: "worse" },
    ]);
  });
});

describe("configDifferences no modo agente", () => {
  const base = makeAgentLoadRun().config;

  it("configurações iguais não têm diferenças", () => {
    expect(configDifferences(base, { ...base })).toEqual([]);
  });

  it("inclui provedor e seleção", () => {
    expect(
      configDifferences(base, {
        ...base,
        provider: "kiro-cli",
        concurrency: 4,
        selection: { case_id: "x", group: null, tags: null },
      }),
    ).toEqual(["provedor", "sessões simultâneas", "seleção de casos"]);
  });

  it("modos diferentes diferem em tudo", () => {
    expect(configDifferences(base, makeLoadRun().config)).toEqual(["modo"]);
  });
});
