import { afterEach, describe, expect, it, vi } from "vitest";

import {
  cancelLoadRun,
  fetchLoadIndex,
  fetchLoadRun,
  fetchLoadTools,
  pollLoadRun,
  startLoadRun,
  type LoadRunState,
} from "@/services/loadApi";

function state(status: LoadRunState["status"]): LoadRunState {
  return {
    run_id: "r1",
    status,
    phase: status === "running" ? "running" : null,
    config: { concurrency: 2, duration_seconds: 10, iterations: null, tools: null, timeout_seconds: 60 },
    load_id: status === "done" ? "20261024_100000_abc1234" : null,
    error: null,
    cancel_requested: false,
    started_at: "",
    finished_at: null,
    progress: null,
    log: [],
  };
}

function response(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return { ok: init.ok ?? true, status: init.status ?? 200, json: async () => body } as Response;
}

function stubFetch(handler: (url: string, init?: RequestInit) => Response) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => handler(url, init));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchLoadIndex", () => {
  it("ordena do mais recente para o mais antigo", async () => {
    stubFetch(() =>
      response({
        runs: [
          { load_id: "a", timestamp: "2026-10-24T09:00:00" },
          { load_id: "b", timestamp: "2026-10-24T11:00:00" },
        ],
      }),
    );
    const runs = await fetchLoadIndex();
    expect(runs.map((r) => r.load_id)).toEqual(["b", "a"]);
  });

  it("sem a pasta results/load ainda (404) devolve lista vazia", async () => {
    stubFetch(() => response({}, { ok: false, status: 404 }));
    expect(await fetchLoadIndex()).toEqual([]);
  });

  it("falha de servidor vira erro com o status", async () => {
    stubFetch(() => response({}, { ok: false, status: 500 }));
    await expect(fetchLoadIndex()).rejects.toThrow("HTTP 500");
  });

  it("lê o index e a carga em /data/results/load/", async () => {
    const mock = stubFetch(() => response({ runs: [] }));
    await fetchLoadIndex();
    await fetchLoadRun("20261024_100000_abc1234");
    expect(mock.mock.calls.map((c) => c[0])).toEqual([
      "data/results/load/index.json",
      "data/results/load/20261024_100000_abc1234.json",
    ]);
  });
});

describe("startLoadRun", () => {
  it("envia o corpo em JSON com o header X-Launcher", async () => {
    const mock = stubFetch(() => response(state("pending")));
    await startLoadRun({ concurrency: 4, duration_seconds: 30, tools: ["docs_list"] });

    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("api/load-runs");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["X-Launcher"]).toBe("1");
    expect(JSON.parse(init?.body as string)).toEqual({
      concurrency: 4,
      duration_seconds: 30,
      tools: ["docs_list"],
    });
  });

  it("mostra o motivo do 409 (outro run ativo)", async () => {
    stubFetch(() => response({ detail: "run abc ainda em andamento" }, { ok: false, status: 409 }));
    await expect(startLoadRun({ concurrency: 1, duration_seconds: 5 })).rejects.toThrow(
      "Falha ao disparar a carga: run abc ainda em andamento",
    );
  });

  it("resume os erros de validação do 422 com o campo", async () => {
    stubFetch(() =>
      response(
        {
          detail: [
            { loc: ["body", "concurrency"], msg: "Input should be less than or equal to 32" },
            { loc: ["body", "tools"], msg: "Value error, tools fora do mix somente leitura: run_start" },
          ],
        },
        { ok: false, status: 422 },
      ),
    );
    await expect(startLoadRun({ concurrency: 99, duration_seconds: 5 })).rejects.toThrow(
      /concurrency: Input should be less than or equal to 32; tools: Value error/,
    );
  });
});

describe("cancelLoadRun", () => {
  it("faz POST em /cancel com o header X-Launcher", async () => {
    const mock = stubFetch(() => response(state("running")));
    await cancelLoadRun("r1");
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("api/load-runs/r1/cancel");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["X-Launcher"]).toBe("1");
  });
});

describe("fetchLoadTools", () => {
  it("devolve as tools e os limites do launcher", async () => {
    stubFetch(() =>
      response({
        tools: [{ tool: "docs_list", group: "docs", calls: 1, available: true, reason: null }],
        limits: { max_concurrency: 32 },
      }),
    );
    const data = await fetchLoadTools();
    expect(data.tools[0].tool).toBe("docs_list");
    expect(data.limits.max_concurrency).toBe(32);
  });
});

describe("pollLoadRun", () => {
  it("para quando a carga termina", async () => {
    const states = [state("running"), state("running"), state("done")];
    stubFetch(() => response(states.shift()));
    const seen: string[] = [];
    const final = await pollLoadRun("r1", (s) => seen.push(s.status), { intervalMs: 1 });
    expect(final.status).toBe("done");
    expect(final.load_id).toBe("20261024_100000_abc1234");
    expect(seen).toEqual(["running", "running", "done"]);
  });

  it("para quando a carga é cancelada no launcher", async () => {
    const states = [state("running"), state("cancelled")];
    stubFetch(() => response(states.shift()));
    const final = await pollLoadRun("r1", () => {}, { intervalMs: 1 });
    expect(final.status).toBe("cancelled");
  });

  it("para de consultar quando o signal é abortado", async () => {
    const mock = stubFetch(() => response(state("running")));
    const controller = new AbortController();
    const polling = pollLoadRun("r1", () => controller.abort(), {
      intervalMs: 50,
      signal: controller.signal,
    });
    await expect(polling).rejects.toBeDefined();
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it("estoura o teto de tempo do polling com erro", async () => {
    stubFetch(() => response(state("running")));
    const final = await pollLoadRun("r1", () => {}, { intervalMs: 1, maxMs: 5 });
    expect(final.status).toBe("error");
    expect(final.error).toMatch(/Timeout de polling/);
  });
});
