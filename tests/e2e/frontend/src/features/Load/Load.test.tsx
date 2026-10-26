import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppNav } from "@/navigation/AppNav";
import type { LoadRunState } from "@/services/loadApi";
import { Load } from "./index";
import { makeLoadRun, stats, toolInfo } from "./fixtures";

const OLDER = makeLoadRun({
  load_id: "20261024_090000_abc1234",
  timestamp: "2026-10-24T09:00:00",
  totals: stats({ throughput_cps: 10, p95_ms: 90 }),
});
const NEWER = makeLoadRun({
  load_id: "20261024_100000_abc1234",
  timestamp: "2026-10-24T10:00:00",
  config: { ...makeLoadRun().config, concurrency: 4 },
  totals: stats({ throughput_cps: 14, p95_ms: 70, error_rate: 0.02, errors: 2, ok: 98 }),
});

function entry(run: typeof OLDER) {
  const t = run.totals;
  return {
    load_id: run.load_id,
    timestamp: run.timestamp,
    version: run.version,
    git_commit_sha: run.git_commit_sha,
    interrupted: false,
    config: run.config,
    summary: {
      calls: t.calls, ok: t.ok, errors: t.errors, timeouts: t.timeouts, error_rate: t.error_rate,
      throughput_cps: t.throughput_cps, p50_ms: t.p50_ms, p95_ms: t.p95_ms, p99_ms: t.p99_ms,
    },
  };
}

const TOOLS = {
  tools: [
    toolInfo({ tool: "deck_list", group: "deck", calls: 1 }),
    toolInfo({ tool: "docs_search", group: "docs", calls: 2 }),
    toolInfo({ tool: "deck_edit_json", group: "deck", calls: 1, writes: true, default: false }),
  ],
  limits: {
    min_concurrency: 1, max_concurrency: 32, min_duration_seconds: 1, max_duration_seconds: 1800,
    max_iterations: 1_000_000, max_timeout_seconds: 1800, default_timeout_seconds: 60,
  },
};

function runState(overrides: Partial<LoadRunState> = {}): LoadRunState {
  return {
    run_id: "r1",
    status: "running",
    phase: "running",
    config: { concurrency: 2, duration_seconds: 30, iterations: null, tools: null, timeout_seconds: 60 },
    load_id: null,
    error: null,
    cancel_requested: false,
    started_at: "",
    finished_at: null,
    progress: {
      phase: "running", elapsed_seconds: 3, duration_seconds: 30,
      clients: { requested: 2, ready: 2, failed: 0, respawns: 0 },
      calls: 42, ok: 42, errors: 0, timeouts: 0, error_rate: 0, throughput_cps: 14,
      p50_ms: 30, p95_ms: 80, p99_ms: 95, max_ms: 99, series: [], resources: null,
    },
    log: [],
    ...overrides,
  };
}

type Handler = (url: string, init?: RequestInit) => { status?: number; body?: unknown } | undefined;

function stubFetch(handler: Handler) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => {
    const hit = handler(url, init);
    if (!hit) return { ok: false, status: 404, json: async () => ({}) } as Response;
    const status = hit.status ?? 200;
    return { ok: status < 400, status, json: async () => hit.body } as Response;
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const recorded: Handler = (url) => {
  if (url === "data/results/load/index.json") return { body: { runs: [entry(OLDER), entry(NEWER)] } };
  if (url === `data/results/load/${OLDER.load_id}.json`) return { body: OLDER };
  if (url === `data/results/load/${NEWER.load_id}.json`) return { body: NEWER };
  return undefined;
};

function renderLoad() {
  return render(
    <MemoryRouter>
      <Load />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Load com o launcher offline", () => {
  it("mostra as cargas gravadas em modo leitura, sem formulário", async () => {
    stubFetch(recorded);
    renderLoad();

    expect(await screen.findByText(/Launcher de testes offline/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Iniciar carga/ })).not.toBeInTheDocument();

    const cards = await screen.findByLabelText("Resumo da carga");
    expect(within(cards).getByText("14.0/s")).toBeInTheDocument();
    expect(within(cards).getByText("2.0%")).toBeInTheDocument();
    expect(within(cards).getByText("70 ms")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Métricas por tool" })).toBeInTheDocument();
  });

  it("compara com a carga anterior e avisa que os parâmetros diferem", async () => {
    stubFetch(recorded);
    renderLoad();

    const comparison = await screen.findByLabelText("Comparação entre cargas");
    expect(within(comparison).getByText(/Comparação: 24\/10\/2026 10:00:00 vs 24\/10\/2026 09:00:00/)).toBeInTheDocument();
    expect(within(comparison).getByText(/parâmetros diferentes \(sessões simultâneas\)/)).toBeInTheDocument();
    expect(within(comparison).getByText(/\+4\.0\/s/)).toBeInTheDocument();
    expect(within(comparison).getByRole("table", { name: "p95 por tool" })).toBeInTheDocument();
  });

  it("escolher Nenhuma remove a comparação", async () => {
    stubFetch(recorded);
    renderLoad();
    await screen.findByLabelText("Comparação entre cargas");

    fireEvent.change(screen.getByLabelText("Comparar com"), { target: { value: "" } });

    await waitFor(() =>
      expect(screen.queryByLabelText("Comparação entre cargas")).not.toBeInTheDocument(),
    );
  });

  it("sem nenhuma carga gravada explica como gerar a primeira", async () => {
    stubFetch(() => undefined);
    renderLoad();
    expect(await screen.findByText(/Nenhuma carga gravada ainda/)).toBeInTheDocument();
  });
});

describe("Load com o launcher no ar", () => {
  const online: Handler = (url, init) => {
    if (url === "api/health") return { body: { ok: true } };
    if (url === "api/load-tools") return { body: TOOLS };
    if (url === "api/load-runs" && init?.method === "POST") return { body: runState({ status: "pending", phase: null, progress: null }) };
    if (url === "api/load-runs") return { body: { runs: [] } };
    if (url === "api/load-runs/r1") return { body: runState() };
    return recorded(url, init);
  };

  it("dispara a carga com o header do launcher e mostra o progresso ao vivo", async () => {
    const mock = stubFetch(online);
    renderLoad();

    fireEvent.change(await screen.findByLabelText(/Sessões simultâneas/), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText(/Duração/), { target: { value: "30" } });
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));

    expect(await screen.findByText("Carga em andamento…")).toBeInTheDocument();
    expect(screen.getByLabelText("Métricas ao vivo")).toHaveTextContent("42");
    expect(screen.getByRole("button", { name: /Parar/ })).toBeInTheDocument();

    const post = mock.mock.calls.find(([url, init]) => url === "api/load-runs" && init?.method === "POST");
    expect(post).toBeDefined();
    expect((post?.[1]?.headers as Record<string, string>)["X-Launcher"]).toBe("1");
    expect(JSON.parse(post?.[1]?.body as string)).toMatchObject({
      concurrency: 2, duration_seconds: 30, tools: null, timeout_seconds: 60,
    });
  });

  it("o mix padrão manda tools nulo; marcar uma que grava manda a lista e refaz a capacidade", async () => {
    const mock = stubFetch(online);
    renderLoad();

    await screen.findByLabelText(/Sessões simultâneas/);
    const capacityUrls = () =>
      mock.mock.calls.map(([url]) => url as string).filter((u) => u.startsWith("api/load-capacity"));
    await waitFor(() => expect(capacityUrls()).toEqual(["api/load-capacity?mode=tools"]));

    fireEvent.click(screen.getByRole("checkbox", { name: "deck_edit_json" }));
    await waitFor(() =>
      expect(capacityUrls().at(-1)).toBe(
        "api/load-capacity?mode=tools&tools=deck_list,docs_search,deck_edit_json",
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    await screen.findByText("Carga em andamento…");
    const post = mock.mock.calls.find(([url, init]) => url === "api/load-runs" && init?.method === "POST");
    expect(JSON.parse(post?.[1]?.body as string).tools).toEqual([
      "deck_list",
      "docs_search",
      "deck_edit_json",
    ]);
  });

  it("mostra o motivo quando há outro run em andamento (409)", async () => {
    stubFetch((url, init) =>
      url === "api/load-runs" && init?.method === "POST"
        ? { status: 409, body: { detail: "run abc123 ainda em andamento" } }
        : online(url, init),
    );
    renderLoad();

    fireEvent.click(await screen.findByRole("button", { name: /Iniciar carga/ }));

    expect(await screen.findByText(/run abc123 ainda em andamento/)).toBeInTheDocument();
  });

  it("Parar chama o cancelamento do launcher", async () => {
    const mock = stubFetch((url, init) =>
      url === "api/load-runs/r1/cancel" && init?.method === "POST"
        ? { body: runState({ cancel_requested: true }) }
        : online(url, init),
    );
    renderLoad();
    fireEvent.click(await screen.findByRole("button", { name: /Iniciar carga/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Parar/ }));

    await waitFor(() =>
      expect(mock.mock.calls.some(([url]) => url === "api/load-runs/r1/cancel")).toBe(true),
    );
  });

  it("retoma o acompanhamento de uma carga que já estava rodando", async () => {
    stubFetch((url, init) =>
      url === "api/load-runs" && !init?.method ? { body: { runs: [runState()] } } : online(url, init),
    );
    renderLoad();
    expect(await screen.findByText("Carga em andamento…")).toBeInTheDocument();
  });
});

describe("AppNav", () => {
  it("marca a área ativa e liga as duas áreas", () => {
    render(
      <MemoryRouter initialEntries={["/carga"]}>
        <AppNav />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Carga" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Carga" })).toHaveAttribute("href", "/carga");
  });
});
