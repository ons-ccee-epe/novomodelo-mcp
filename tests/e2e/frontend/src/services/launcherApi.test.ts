import { afterEach, describe, expect, it, vi } from "vitest";

import { pollRun, type RunState } from "@/services/launcherApi";

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
