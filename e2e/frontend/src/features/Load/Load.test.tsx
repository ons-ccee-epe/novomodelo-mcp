import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LoadRunState } from "@/services/loadApi";
import { History } from "@/features/History";
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

function renderLoad(path = "/historico/carga") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/carga" element={<Load />} />
        <Route path="/historico/carga" element={<History />} />
        <Route path="/historico/carga/:loadId" element={<History />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Load com o launcher offline", () => {
  it("a aba de carga avisa que o launcher está offline e aponta o Histórico", async () => {
    stubFetch(recorded);
    renderLoad("/carga");

    expect(await screen.findByText(/Launcher de testes offline/)).toBeInTheDocument();
    expect(screen.getByText(/As cargas já gravadas continuam no Histórico/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Iniciar carga/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Resumo da carga")).not.toBeInTheDocument();
  });

  it("o Histórico de carga lista as cargas e abre a mais recente, mesmo sem o launcher", async () => {
    stubFetch(recorded);
    renderLoad();

    const list = await screen.findByRole("list", { name: "Cargas gravadas" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((li) => li.getAttribute("data-load-id"))).toEqual([
      NEWER.load_id,
      OLDER.load_id,
    ]);
    expect(items[0]).toHaveAttribute("aria-current", "true");
    expect(within(items[0]).getByText("Tools")).toBeInTheDocument();
    expect(within(items[0]).getByText(/4 sessões · 10 s · 14\.0\/s · p95 70 ms/)).toBeInTheDocument();
    expect(within(items[0]).getByText("erro")).toBeInTheDocument();

    const cards = await screen.findByLabelText("Resumo da carga", {}, { timeout: 3000 });
    expect(
      screen.getByRole("heading", { name: /Carga de tools — 24\/10\/2026 10:00:00/ }),
    ).toBeInTheDocument();
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

  it("a URL escolhe a carga exibida e marca o card dela", async () => {
    stubFetch(recorded);
    renderLoad(`/historico/carga/${OLDER.load_id}`);

    expect(
      await screen.findByRole("heading", { name: /Carga de tools — 24\/10\/2026 09:00:00/ }),
    ).toBeInTheDocument();
    const selected = screen
      .getAllByRole("listitem")
      .find((li) => li.getAttribute("aria-current") === "true");
    expect(selected).toHaveAttribute("data-load-id", OLDER.load_id);
    expect(screen.queryByLabelText("Comparação entre cargas")).not.toBeInTheDocument();
  });

  it("os detalhes vêm recolhidos", async () => {
    stubFetch(recorded);
    renderLoad();
    const details = await screen.findByLabelText("Detalhes da carga");
    expect(details.tagName).toBe("DETAILS");
    expect(details).not.toHaveAttribute("open");
  });

  it("recolher a lista deixa só o botão de mostrar", async () => {
    stubFetch(recorded);
    renderLoad();
    fireEvent.click(await screen.findByRole("button", { name: "Recolher a lista de cargas" }));
    expect(screen.queryByRole("list", { name: "Cargas gravadas" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mostrar a lista de cargas" })).toBeInTheDocument();
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
    expect(await screen.findByText(/Dispare uma carga em Testes de Carga/)).toBeInTheDocument();
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
    renderLoad("/carga");

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
    renderLoad("/carga");

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
    renderLoad("/carga");

    fireEvent.click(await screen.findByRole("button", { name: /Iniciar carga/ }));

    expect(await screen.findByText(/run abc123 ainda em andamento/)).toBeInTheDocument();
  });

  it("Parar chama o cancelamento do launcher", async () => {
    const mock = stubFetch((url, init) =>
      url === "api/load-runs/r1/cancel" && init?.method === "POST"
        ? { body: runState({ cancel_requested: true }) }
        : online(url, init),
    );
    renderLoad("/carga");
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
    renderLoad("/carga");
    expect(await screen.findByText("Carga em andamento…")).toBeInTheDocument();
  });

  it("ao concluir mostra o resumo gravado e Ver no Histórico abre a carga", async () => {
    stubFetch((url, init) =>
      url === "api/load-runs/r1"
        ? { body: runState({ status: "done", phase: null, load_id: OLDER.load_id }) }
        : online(url, init),
    );
    renderLoad("/carga");
    fireEvent.click(await screen.findByRole("button", { name: /Iniciar carga/ }));

    const summary = await screen.findByLabelText("Resumo da carga concluída");
    expect(summary).toHaveTextContent("Vazão 10.0/s");
    expect(summary).toHaveTextContent("p95 90 ms");
    expect(screen.queryByLabelText("Métricas ao vivo")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ver no Histórico" }));

    expect(
      await screen.findByRole("heading", { name: /Carga de tools — 24\/10\/2026 09:00:00/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Carga" })).toHaveAttribute("aria-current", "page");
  });

  it("o mix vem resumido no padrão e a lista completa fica em Personalizar", async () => {
    stubFetch(online);
    renderLoad("/carga");

    const summary = await screen.findByText(/2 de 3 tools · padrão: só leitura, sem as pesadas/);
    expect(summary.closest("details")).not.toHaveAttribute("open");

    fireEvent.click(screen.getByRole("checkbox", { name: "deck_edit_json" }));
    expect(screen.getByText(/3 de 3 tools · personalizado · 1 gravam/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "padrão" }));
    expect(screen.getByText(/2 de 3 tools · padrão/)).toBeInTheDocument();
  });
});
