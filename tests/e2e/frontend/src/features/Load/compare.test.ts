import { describe, expect, it } from "vitest";

import { compareStats, compareToolP95, configDifferences, trendOf } from "./compare";
import { makeLoadRun, stats } from "./fixtures";
import { fmtLoadId, fmtMs, fmtPercent } from "./format";

describe("trendOf", () => {
  it("menor é melhor para latência e erro", () => {
    expect(trendOf(-5, true)).toBe("better");
    expect(trendOf(5, true)).toBe("worse");
  });

  it("maior é melhor para vazão", () => {
    expect(trendOf(2, false)).toBe("better");
    expect(trendOf(-2, false)).toBe("worse");
  });

  it("sem variação ou sem dado é neutro", () => {
    expect(trendOf(0, true)).toBe("flat");
    expect(trendOf(null, false)).toBe("flat");
  });
});

describe("compareStats", () => {
  it("calcula delta, variação relativa e tendência de cada métrica", () => {
    const deltas = compareStats(
      stats({ throughput_cps: 12, error_rate: 0.1, p50_ms: 30, p95_ms: 80, p99_ms: 100 }),
      stats({ throughput_cps: 10, error_rate: 0, p50_ms: 40, p95_ms: 80, p99_ms: 100 }),
    );
    const byKey = Object.fromEntries(deltas.map((d) => [d.spec.key, d]));

    expect(byKey.throughput_cps.delta).toBe(2);
    expect(byKey.throughput_cps.relative).toBeCloseTo(0.2);
    expect(byKey.throughput_cps.trend).toBe("better");
    expect(byKey.error_rate.trend).toBe("worse");
    expect(byKey.error_rate.relative).toBeNull();
    expect(byKey.p50_ms.trend).toBe("better");
    expect(byKey.p95_ms.trend).toBe("flat");
  });

  it("lado sem latência (nenhuma chamada ok) vira sem dados, não zero", () => {
    const p50 = compareStats(stats({ p50_ms: null }), stats({ p50_ms: 30 })).find(
      (d) => d.spec.key === "p50_ms",
    );
    expect(p50?.delta).toBeNull();
    expect(p50?.trend).toBe("flat");
  });
});

describe("compareToolP95", () => {
  it("compara só as tools presentes nas duas cargas", () => {
    const current = makeLoadRun({
      per_tool: { a: stats({ p95_ms: 100 }), b: stats({ p95_ms: 50 }), nova: stats() },
    });
    const previous = makeLoadRun({
      per_tool: { a: stats({ p95_ms: 80 }), b: stats({ p95_ms: 60 }) },
    });
    const rows = compareToolP95(current, previous);
    expect(rows.map((r) => r.tool)).toEqual(["a", "b"]);
    expect(rows[0]).toMatchObject({ delta: 20, trend: "worse" });
    expect(rows[1]).toMatchObject({ delta: -10, trend: "better" });
  });
});

describe("configDifferences", () => {
  const base = makeLoadRun().config;

  it("configurações iguais não têm diferenças", () => {
    expect(configDifferences(base, { ...base })).toEqual([]);
  });

  it("lista os parâmetros que mudaram", () => {
    expect(
      configDifferences(base, { ...base, concurrency: 8, tools: ["docs_list"], iterations: 5 }),
    ).toEqual(["sessões simultâneas", "iterações", "tools"]);
  });
});

describe("formatação", () => {
  it("latência em ms ou s, e ausente como traço", () => {
    expect(fmtMs(42.4)).toBe("42 ms");
    expect(fmtMs(1500)).toBe("1.50 s");
    expect(fmtMs(null)).toBe("—");
  });

  it("taxa de erro vem como fração", () => {
    expect(fmtPercent(0.025)).toBe("2.5%");
  });

  it("o id da carga vira data e hora locais", () => {
    expect(fmtLoadId("20261024_101530_abc1234")).toBe("24/10/2026 10:15:30");
    expect(fmtLoadId("outro")).toBe("outro");
  });
});
