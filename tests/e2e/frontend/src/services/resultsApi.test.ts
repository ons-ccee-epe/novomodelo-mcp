import { describe, expect, it, vi, beforeEach } from "vitest";
import { fetchBaselineFile, fetchMetricsHistory } from "@/services/resultsApi";

describe("fetchMetricsHistory", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("parseia JSONL ignorando linhas vazias e malformadas, ordenando por timestamp asc", async () => {
    const jsonl = [
      '{"batch_id":"b2","timestamp":"2026-01-02T00:00:00","pct_mcp_used":90,"pct_correct_tool":80,"pct_correct_result":70,"avg_latency_ms":100}',
      "",
      "{linha quebrada",
      '{"batch_id":"b1","timestamp":"2026-01-01T00:00:00","pct_mcp_used":50,"pct_correct_tool":40,"pct_correct_result":30,"avg_latency_ms":200}',
    ].join("\n");

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, text: async () => jsonl }) as unknown as Response),
    );

    const records = await fetchMetricsHistory();
    expect(records).toHaveLength(2);
    expect(records[0].batch_id).toBe("b1"); // mais antigo primeiro
    expect(records[1].batch_id).toBe("b2");
  });

  it("retorna lista vazia quando o arquivo nao existe", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 404 }) as unknown as Response),
    );
    const records = await fetchMetricsHistory();
    expect(records).toEqual([]);
  });
});

describe("fetchBaselineFile", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  function stubJson(body: unknown, ok = true) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok, status: ok ? 200 : 404, json: async () => body }) as unknown as Response),
    );
  }

  it("le o formato novo por conjunto", async () => {
    stubJson({ baselines: { todos: "b1", "grupo:deck": "b2" } });
    expect(await fetchBaselineFile()).toEqual({
      baselines: { todos: "b1", "grupo:deck": "b2" },
      legacyId: null,
    });
  });

  it("le o formato antigo como legacyId", async () => {
    stubJson({ batch_id: "b0" });
    expect(await fetchBaselineFile()).toEqual({ baselines: {}, legacyId: "b0" });
  });

  it("arquivo ausente vira vazio", async () => {
    stubJson({}, false);
    expect(await fetchBaselineFile()).toEqual({ baselines: {}, legacyId: null });
  });
});
