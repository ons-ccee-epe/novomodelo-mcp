import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearBaseline,
  fetchCommandPreview,
  pollRun,
  setBaseline,
  type RunState,
} from "@/services/launcherApi";

function runState(status: RunState["status"]): RunState {
  return {
    run_id: "r1",
    provider: "kiro-cli",
    status,
    total: 1,
    completed: status === "done" ? 1 : 0,
    current: null,
    batch_id: null,
    error: null,
    cancel_requested: false,
    started_at: "",
    finished_at: null,
    log: [],
    results: [],
  };
}

function stubFetchSequence(states: RunState[]) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    json: async () => states.shift() ?? runState("running"),
  }) as unknown as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("pollRun", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("para quando o run termina", async () => {
    stubFetchSequence([runState("running"), runState("done")]);
    const updates: string[] = [];
    const final = await pollRun("r1", (s) => updates.push(s.status), { intervalMs: 1 });
    expect(final.status).toBe("done");
    expect(updates).toEqual(["running", "done"]);
  });

  it("para quando o run é cancelado no launcher", async () => {
    stubFetchSequence([runState("running"), runState("cancelled")]);
    const final = await pollRun("r1", () => {}, { intervalMs: 1 });
    expect(final.status).toBe("cancelled");
  });

  it("para de consultar quando o signal é abortado", async () => {
    const fetchMock = stubFetchSequence([]);
    const controller = new AbortController();
    const polling = pollRun("r1", () => controller.abort(), {
      intervalMs: 50,
      signal: controller.signal,
    });
    await expect(polling).rejects.toBeDefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("baseline e preview de comando", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubOk(body: unknown = {}) {
    const fetchMock = vi.fn(
      async () => ({ ok: true, json: async () => body }) as unknown as Response,
    );
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("setBaseline faz PUT com header e body", async () => {
    const fetchMock = stubOk();
    await setBaseline("grupo:bridge+deck", "b1");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("api/baselines/grupo%3Abridge%2Bdeck");
    expect(init.method).toBe("PUT");
    expect((init.headers as Record<string, string>)["X-Launcher"]).toBe("1");
    expect(init.body).toBe('{"batch_id":"b1"}');
  });

  it("clearBaseline faz DELETE com header", async () => {
    const fetchMock = stubOk();
    await clearBaseline("todos");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("api/baselines/todos");
    expect(init.method).toBe("DELETE");
    expect((init.headers as Record<string, string>)["X-Launcher"]).toBe("1");
  });

  it("fetchCommandPreview monta a query", async () => {
    const preview = { conjunto: "todos", total: 2, terminal: null, terminal_note: null, agent: "x" };
    const fetchMock = stubOk(preview);
    expect(await fetchCommandPreview({ provider: "kiro-cli", tags: ["docs"] })).toEqual(preview);
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe(
      "api/command-preview?provider=kiro-cli&tags=docs",
    );
  });
});
