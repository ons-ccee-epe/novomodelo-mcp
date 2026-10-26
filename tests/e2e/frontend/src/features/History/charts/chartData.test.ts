import { describe, expect, it } from "vitest";

import { makeBatch } from "@/shared/fixtures.testutil";
import type { BatchResult, TestResult } from "@/shared/types";
import { funnel, latencyRows, passByGroup, statusCounts, toolsPerQuestion, toolUsage } from "./chartData";

function fixture(): BatchResult {
  const b = makeBatch("b1", [
    ["q1", "pass", "a"],
    ["q2", "fail", "a"],
    ["q3", "pass", "b"],
    ["q4", "pass", "b"],
  ]);
  const extra: Array<Partial<TestResult>> = [
    { latency_ms: 100, tool_latency_ms: 40, all_tool_calls: [{ name: "a", args: {} }] },
    { latency_ms: 300, tool_latency_ms: null, all_tool_calls: [] },
    {
      latency_ms: 200,
      tool_latency_ms: 50,
      all_tool_calls: [
        { name: "a", args: {} },
        { name: "b", args: {} },
        { name: "a", args: {} },
      ],
    },
    {
      latency_ms: 50,
      tool_latency_ms: 5,
      all_tool_calls: [
        { name: "a", args: {} },
        { name: "b", args: {} },
      ],
    },
  ];
  b.test_results = b.test_results.map((r, i) => ({ ...r, ...extra[i] }) as TestResult);
  b.metrics = {
    pct_mcp_used: 90,
    pct_correct_tool: 80,
    pct_correct_result: 70,
  } as BatchResult["metrics"];
  b.metrics_by_group = {
    docs: { pct_pass: 50 },
    sim: { pct_pass: 100 },
  } as unknown as BatchResult["metrics_by_group"];
  return b;
}

describe("chartData", () => {
  it("statusCounts omite zeros", () => {
    expect(statusCounts(fixture())).toEqual([
      { status: "pass", count: 3 },
      { status: "fail", count: 1 },
    ]);
  });

  it("latencyRows ordena por total desc e trata tool nulo como 0", () => {
    const rows = latencyRows(fixture());
    expect(rows.map((r) => r.test_id)).toEqual(["q2", "q3", "q1", "q4"]);
    expect(rows[0]).toEqual({ test_id: "q2", total_ms: 300, tool_ms: 0, status: "fail" });
  });

  it("toolUsage conta por nome, desc", () => {
    expect(toolUsage(fixture())).toEqual([
      { tool: "a", calls: 4 },
      { tool: "b", calls: 2 },
    ]);
  });

  it("toolsPerQuestion sempre traz os quatro buckets", () => {
    expect(toolsPerQuestion(fixture())).toEqual([
      { bucket: "0", count: 1 },
      { bucket: "1", count: 1 },
      { bucket: "2", count: 1 },
      { bucket: "3+", count: 1 },
    ]);
    const empty = makeBatch("e", []);
    expect(toolsPerQuestion(empty).map((r) => r.count)).toEqual([0, 0, 0, 0]);
  });

  it("passByGroup lê pct_pass", () => {
    expect(passByGroup(fixture())).toEqual([
      { group: "docs", pct: 50 },
      { group: "sim", pct: 100 },
    ]);
  });

  it("funnel segue a ordem dos passos", () => {
    expect(funnel(fixture())).toEqual([
      { step: "Usou o MCP", pct: 90 },
      { step: "Tool certa", pct: 80 },
      { step: "Resultado certo", pct: 70 },
    ]);
  });
});
