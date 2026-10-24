import { describe, expect, it } from "vitest";

import type { BatchResult, MetricsHistoryRecord } from "@/shared/types";
import { computeAlerts, previousRecord } from "./alertRules";

function record(batch_id: string, overrides: Partial<MetricsHistoryRecord> = {}): MetricsHistoryRecord {
  return {
    batch_id,
    timestamp: batch_id,
    pct_mcp_used: 100,
    pct_correct_tool: 100,
    pct_correct_result: 100,
    avg_latency_ms: 1000,
    ...overrides,
  };
}

function batch(batch_id: string, metrics: Partial<BatchResult["metrics"]> = {}): BatchResult {
  return {
    batch_id,
    metrics: {
      pct_mcp_used: 100,
      pct_correct_tool: 100,
      pct_correct_result: 100,
      avg_latency_ms: 1000,
      p95_latency_ms: 1000,
      ...metrics,
    },
  } as BatchResult;
}

describe("previousRecord", () => {
  it("devolve o registro imediatamente anterior ao da bateria", () => {
    const history = [record("b1"), record("b2"), record("b3")];
    expect(previousRecord(history, "b3")?.batch_id).toBe("b2");
  });

  it("devolve null quando a bateria não está no histórico", () => {
    expect(previousRecord([record("b1"), record("b2")], "fora")).toBeNull();
  });
});

describe("computeAlerts", () => {
  it("sem variação relevante não gera alerta", () => {
    const history = [record("b1"), record("b2")];
    expect(computeAlerts(batch("b2"), history, null)).toEqual([]);
  });

  it("queda de uso do MCP acima do limiar crítico gera alerta crítico", () => {
    const history = [record("b1"), record("b2", { pct_mcp_used: 80 })];
    const alerts = computeAlerts(batch("b2", { pct_mcp_used: 80 }), history, null);
    expect(alerts).toHaveLength(1);
    expect(alerts[0].level).toBe("critical");
  });

  it("queda moderada de uso do MCP gera aviso", () => {
    const history = [record("b1"), record("b2", { pct_mcp_used: 93 })];
    const alerts = computeAlerts(batch("b2", { pct_mcp_used: 93 }), history, null);
    expect(alerts.map((a) => a.level)).toEqual(["warning"]);
  });

  it("queda de acerto de tool vs baseline gera aviso", () => {
    const alerts = computeAlerts(batch("b2", { pct_correct_tool: 80 }), [], batch("base"));
    expect(alerts.map((a) => a.message)).toEqual([expect.stringContaining("Correct tool")]);
  });

  it("latência compara com as baterias anteriores à selecionada, não com as mais novas", () => {
    const history = [record("b1"), record("b2"), record("b3", { avg_latency_ms: 5000 })];
    const alerts = computeAlerts(batch("b2", { avg_latency_ms: 1000 }), history, null);
    expect(alerts).toEqual([]);
  });

  it("latência acima do limiar vs média anterior gera aviso", () => {
    const history = [record("b1"), record("b2"), record("b3", { avg_latency_ms: 2000 })];
    const alerts = computeAlerts(batch("b3", { avg_latency_ms: 2000 }), history, null);
    expect(alerts.map((a) => a.message)).toEqual([expect.stringContaining("latência")]);
  });
});
