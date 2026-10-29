import { describe, expect, it } from "vitest";

import { loteSintetico } from "@/data/fixtures.testutil";
import type { BatchResult } from "@/shared/types";
import {
  funnel,
  latencyLegend,
  latencyRows,
  passByGroup,
  statusColor,
  statusCounts,
  toolsPerQuestion,
  toolUsage,
} from "./chartData";

function fixture(): BatchResult {
  return loteSintetico("b1", "2026-01-01T00:00:00Z", [
    { caso: "q1", duracao_s: 0.1, tools: [["docs_list", 0.04]] },
    { caso: "q2", estado: "falhou", duracao_s: 0.3, tools: [] },
    {
      caso: "q3",
      duracao_s: 0.2,
      tools: [
        ["deck_list", 0.02],
        ["docs_list", 0.01],
        ["deck_list", 0.02],
      ],
    },
    {
      caso: "q4",
      duracao_s: 0.05,
      tools: [
        ["deck_list", 0.003],
        ["docs_list", 0.002],
      ],
    },
  ]);
}

describe("chartData sobre registros do conjunto tools", () => {
  it("statusCounts omite zeros", () => {
    expect(statusCounts(fixture())).toEqual([
      { status: "pass", count: 3 },
      { status: "fail", count: 1 },
    ]);
  });

  it("statusCounts conta erro de infra", () => {
    const b = loteSintetico("b", "2026-01-01T00:00:00Z", [
      { caso: "q1", estado: "erro_infra" },
      { caso: "q2", estado: "pulado" },
    ]);
    expect(statusCounts(b)).toEqual([
      { status: "erro_infra", count: 1 },
      { status: "skip", count: 1 },
    ]);
  });

  it("latencyRows ordena por total desc e trata tool nulo como 0", () => {
    const rows = latencyRows(fixture()).map((r) => ({
      ...r,
      total_ms: Math.round(r.total_ms),
      tool_ms: Math.round(r.tool_ms),
    }));
    expect(rows.map((r) => r.test_id)).toEqual(["q2", "q3", "q1", "q4"]);
    expect(rows[0]).toEqual({ test_id: "q2", total_ms: 300, tool_ms: 0, status: "fail" });
    expect(rows[3]).toEqual({ test_id: "q4", total_ms: 50, tool_ms: 5, status: "pass" });
  });

  it("toolUsage conta por nome, desc", () => {
    expect(toolUsage(fixture())).toEqual([
      { tool: "docs_list", calls: 3 },
      { tool: "deck_list", calls: 3 },
    ]);
  });

  it("toolsPerQuestion sempre traz os quatro buckets", () => {
    expect(toolsPerQuestion(fixture())).toEqual([
      { bucket: "0", count: 1 },
      { bucket: "1", count: 1 },
      { bucket: "2", count: 1 },
      { bucket: "3+", count: 1 },
    ]);
    const vazio = loteSintetico("e", "2026-01-01T00:00:00Z", []);
    expect(toolsPerQuestion(vazio).map((r) => r.count)).toEqual([0, 0, 0, 0]);
  });

  it("passByGroup agrupa pela primeira tool chamada", () => {
    expect(passByGroup(fixture())).toEqual([
      { group: "docs", pct: 100 },
      { group: "other", pct: 0 },
      { group: "deck", pct: 100 },
    ]);
  });

  it("funnel segue a ordem dos passos e usa o estado quando falta a métrica", () => {
    expect(funnel(fixture())).toEqual([
      { step: "Usou o MCP", pct: 75 },
      { step: "Tool certa", pct: 75 },
      { step: "Resultado certo", pct: 75 },
    ]);
  });

  it("statusColor mapeia cada status para o token --nm-*", () => {
    expect(statusColor("pass")).toBe("var(--nm-pass)");
    expect(statusColor("fail")).toBe("var(--nm-fail)");
    expect(statusColor("partial")).toBe("var(--nm-partial)");
    expect(statusColor("timeout")).toBe("var(--nm-timeout)");
    expect(statusColor("erro_infra")).toBe("var(--nm-erro_infra)");
    expect(statusColor("skip")).toBe("var(--nm-skip)");
  });

  it("latencyLegend lista só os status presentes mais o tempo na tool", () => {
    expect(latencyLegend(fixture())).toEqual([
      { label: "Aprovada", color: "var(--nm-pass)" },
      { label: "Falhou", color: "var(--nm-fail)" },
      { label: "Tempo na tool", color: "var(--nm-text-muted)" },
    ]);
  });
});
