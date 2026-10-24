import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { BatchResult } from "@/shared/types";
import { Dashboard } from "./index";

const BATCH: BatchResult = {
  batch_id: "20260101_000000_abc",
  timestamp: "2026-01-01T00:00:00",
  cobre_mcp_version: "0.0.0",
  git_commit_sha: "abc",
  environment: "local",
  total_tests: 1,
  passed: 1,
  partial: 0,
  failed: 0,
  skipped: 0,
  timeout: 0,
  test_results: [
    {
      test_id: "deck-list-newave",
      query: "Liste os arquivos do deck",
      expected_tool: "deck_list",
      expected_tools: null,
      actual_tool: "deck_list",
      all_tool_calls: [{ name: "deck_list", args: {} }],
      status: "pass",
      latency_ms: 1200,
      tool_latency_ms: null,
      mcp_used: true,
      correct_tool: true,
      correct_result: true,
      agent_response: "ok",
      error_message: null,
      tags: ["deck"],
      validation_checks: [],
    },
  ],
  metrics: {
    pct_mcp_used: 100,
    pct_correct_tool: 100,
    pct_correct_result: 100,
    avg_latency_ms: 1200,
    p95_latency_ms: 1200,
  },
  metrics_by_tag: {},
  metrics_by_group: {},
};

const ROUTES: Record<string, unknown> = {
  "data/results/index.json": {
    batches: [
      {
        batch_id: BATCH.batch_id,
        timestamp: BATCH.timestamp,
        version: "0.0.0",
        summary: { total: 1, passed: 1, failed: 0, skipped: 0, timeout: 0 },
      },
    ],
  },
  [`data/results/${BATCH.batch_id}.json`]: BATCH,
};

function fakeFetch(url: string): Promise<Response> {
  const body = ROUTES[url];
  if (body === undefined) return Promise.resolve({ ok: false, status: 404 } as Response);
  return Promise.resolve({
    ok: true,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as Response);
}

describe("Dashboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renderiza a bateria e avisa que o launcher está offline", async () => {
    vi.stubGlobal("fetch", vi.fn(fakeFetch));
    render(
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Launcher de testes offline/)).toBeInTheDocument();
    expect(await screen.findByText("deck-list-newave")).toBeInTheDocument();
    expect(screen.getByText(/Sistema saudável/)).toBeInTheDocument();
    expect(screen.getByLabelText("Status")).toBeInTheDocument();
  });
});
