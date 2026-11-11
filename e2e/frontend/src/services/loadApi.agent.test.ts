import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchLoadCapacity, fetchLoadCases, startLoadRun, type LoadRunState } from "@/services/loadApi";

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

describe("fetchLoadCases", () => {
  it("devolve os casos (com os inelegíveis) e os limites do agente", async () => {
    const mock = stubFetch(() =>
      response({
        cases: [
          { id: "a", group: "docs", available: true, reason: null, writes: false, heavy: false },
          { id: "b", group: "run", available: false, reason: "dispara o solver", writes: true, heavy: true },
        ],
        limits: { max_concurrency: 8, default_timeout_seconds: null },
      }),
    );
    const data = await fetchLoadCases();
    expect(mock.mock.calls[0][0]).toBe("api/load-cases");
    expect(data.cases[1].reason).toBe("dispara o solver");
    expect(data.limits.max_concurrency).toBe(8);
    expect(data.limits.default_timeout_seconds).toBeNull();
  });

  it("falha com o motivo do launcher", async () => {
    stubFetch(() => response({ detail: "cases.yaml ausente" }, { ok: false, status: 500 }));
    await expect(fetchLoadCases()).rejects.toThrow(
      "Falha ao carregar os casos da carga: cases.yaml ausente",
    );
  });

  it("404 = launcher antigo, sem a rota: pede para reiniciá-lo", async () => {
    stubFetch(() => response({ detail: "Not Found" }, { ok: false, status: 404 }));
    await expect(fetchLoadCases()).rejects.toThrow(/reinicie-o \(npm run dev:launcher\)/);
    await expect(fetchLoadCapacity("agent", "claude")).rejects.toThrow(/reinicie-o/);
  });
});

describe("fetchLoadCapacity", () => {
  it("modo tools: só o modo na query string", async () => {
    const mock = stubFetch(() => response({ mode: "tools", recommended: 6 }));
    const capacity = await fetchLoadCapacity("tools", "claude");
    expect(mock.mock.calls[0][0]).toBe("api/load-capacity?mode=tools");
    expect(capacity.recommended).toBe(6);
  });

  it("modo agent: inclui o provedor", async () => {
    const mock = stubFetch(() => response({ mode: "agent", recommended: 2 }));
    await fetchLoadCapacity("agent", "claude");
    expect(mock.mock.calls[0][0]).toBe("api/load-capacity?mode=agent&provider=claude");
  });

  it("modo tools: a lista de tools vai separada por vírgula; sem lista (ou vazia), o mix padrão", async () => {
    const mock = stubFetch(() => response({ mode: "tools", recommended: 3 }));
    await fetchLoadCapacity("tools", null, { tools: ["deck_list", "bridge_check_newave"] });
    expect(mock.mock.calls[0][0]).toBe("api/load-capacity?mode=tools&tools=deck_list,bridge_check_newave");
    await fetchLoadCapacity("tools", null, { tools: null });
    expect(mock.mock.calls[1][0]).toBe("api/load-capacity?mode=tools");
    await fetchLoadCapacity("tools", null, { tools: [] });
    expect(mock.mock.calls[2][0]).toBe("api/load-capacity?mode=tools");
  });

  it("modo agent: um caso ou um grupo (nunca os dois); sem escopo, todos os casos", async () => {
    const mock = stubFetch(() => response({ mode: "agent", recommended: 2 }));
    await fetchLoadCapacity("agent", "claude", { group: "deck" });
    expect(mock.mock.calls[0][0]).toBe("api/load-capacity?mode=agent&provider=claude&group=deck");
    await fetchLoadCapacity("agent", "claude", { caseId: "deck_list#c" });
    expect(mock.mock.calls[1][0]).toBe("api/load-capacity?mode=agent&provider=claude&case_id=deck_list%23c");
    await fetchLoadCapacity("agent", "claude", { caseId: "a#b", group: "deck" });
    expect(mock.mock.calls[2][0]).toBe("api/load-capacity?mode=agent&provider=claude&case_id=a%23b");
    await fetchLoadCapacity("agent", "claude", {});
    expect(mock.mock.calls[3][0]).toBe("api/load-capacity?mode=agent&provider=claude");
  });

  it("a seleção do outro modo é ignorada", async () => {
    const mock = stubFetch(() => response({ mode: "tools", recommended: 6 }));
    await fetchLoadCapacity("tools", null, { group: "deck", caseId: "x" });
    expect(mock.mock.calls[0][0]).toBe("api/load-capacity?mode=tools");
    await fetchLoadCapacity("agent", "claude", { tools: ["deck_list"] });
    expect(mock.mock.calls[1][0]).toBe("api/load-capacity?mode=agent&provider=claude");
  });

  it("modo agent sem provedor escolhido omite o parâmetro", async () => {
    const mock = stubFetch(() => response({ mode: "agent", recommended: 2 }));
    await fetchLoadCapacity("agent", null);
    expect(mock.mock.calls[0][0]).toBe("api/load-capacity?mode=agent");
  });
});

describe("startLoadRun no modo agente", () => {
  const pending = {
    run_id: "r1",
    status: "pending",
    phase: null,
    config: { mode: "agent" },
  } as unknown as LoadRunState;

  it("envia o corpo do agente com o header X-Launcher", async () => {
    const mock = stubFetch(() => response(pending));
    await startLoadRun({
      mode: "agent",
      concurrency: 2,
      duration_seconds: 60,
      iterations: null,
      timeout_seconds: null,
      provider: "claude",
      group: "docs",
    });
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("api/load-runs");
    expect((init?.headers as Record<string, string>)["X-Launcher"]).toBe("1");
    expect(JSON.parse(init?.body as string)).toEqual({
      mode: "agent",
      concurrency: 2,
      duration_seconds: 60,
      iterations: null,
      timeout_seconds: null,
      provider: "claude",
      group: "docs",
    });
  });

  it("422 com detail em texto (provedor ausente, nenhum caso elegível)", async () => {
    stubFetch(() =>
      response({ detail: "provedor claude não está instalado" }, { ok: false, status: 422 }),
    );
    await expect(
      startLoadRun({ mode: "agent", concurrency: 2, duration_seconds: 60, provider: "claude" }),
    ).rejects.toThrow("Falha ao disparar a carga: provedor claude não está instalado");
  });
});
