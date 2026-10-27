import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LoadIndexEntry, SavedLoadRun } from "@/shared/types";
import { isAgentRun } from "@/shared/types";
import { History } from "@/features/History";
import { Load } from "./index";
import { agentStats, makeAgentLoadRun, makeLoadRun, makeSandbox, stats } from "./fixtures";

function entry(run: SavedLoadRun): LoadIndexEntry {
  const t = run.totals;
  const base = {
    load_id: run.load_id,
    timestamp: run.timestamp,
    version: run.version,
    git_commit_sha: run.git_commit_sha,
    interrupted: false,
  };
  const summary = {
    calls: t.calls,
    ok: t.ok,
    errors: t.errors,
    timeouts: t.timeouts,
    error_rate: t.error_rate,
    throughput_cps: t.throughput_cps,
    p50_ms: t.p50_ms,
    p95_ms: t.p95_ms,
    p99_ms: t.p99_ms,
  };
  if (isAgentRun(run)) {
    return {
      ...base,
      mode: "agent",
      config: run.config,
      summary: { ...summary, throughput_cpm: run.totals.throughput_cpm, pass_rate: run.totals.pass_rate },
    };
  }
  return { ...base, config: run.config, summary };
}

function stubRecorded(runs: SavedLoadRun[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "data/results/load/index.json") {
        return { ok: true, status: 200, json: async () => ({ runs: runs.map(entry) }) } as Response;
      }
      const hit = runs.find((r) => url === `data/results/load/${r.load_id}.json`);
      if (hit) return { ok: true, status: 200, json: async () => hit } as Response;
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    }),
  );
}

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

const TOOLS_RUN = makeLoadRun({
  load_id: "20261024_090000_abc1234",
  timestamp: "2026-10-24T09:00:00",
  totals: stats(),
});
const AGENT_OLD = makeAgentLoadRun({
  load_id: "20261024_100000_abc1234",
  timestamp: "2026-10-24T10:00:00",
  totals: agentStats({ throughput_cpm: 1.0, pass_rate: 0.7, p95_ms: 25000 }),
});
const AGENT_NEW = makeAgentLoadRun();

describe("Load com uma carga do modo agente", () => {
  it("mostra cards, tabela por caso e detalhes do agente", async () => {
    stubRecorded([TOOLS_RUN, AGENT_NEW]);
    renderLoad();

    const cards = await screen.findByLabelText("Resumo da carga");
    expect(within(cards).getByText("Sessões simultâneas (Claude Code)")).toBeInTheDocument();
    expect(within(cards).getByText("1.3 casos/min")).toBeInTheDocument();
    expect(within(cards).getByText("80.0%")).toBeInTheDocument();
    expect(within(cards).getByText("2.5")).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Métricas por caso" });
    expect(within(table).getByText("docs_search#a")).toBeInTheDocument();
    expect(within(table).getByText("docs_list#b")).toBeInTheDocument();

    const details = screen.getByLabelText("Detalhes da carga");
    expect(within(details).getByText("Claude Code (claude)")).toBeInTheDocument();
    expect(within(details).getByText("grupo docs")).toBeInTheDocument();
    expect(within(details).getByText("o de cada caso")).toBeInTheDocument();
    expect(within(details).getByText("Recursos (agentes + servidores)")).toBeInTheDocument();
    expect(within(details).getByRole("table", { name: "Erros agrupados" })).toHaveTextContent(
      "estourou 90 s",
    );
    expect(within(details).getByText("Casos fora da carga (1)")).toBeInTheDocument();
    expect(screen.getByText("Casos concluídos por bucket de 5 s")).toBeInTheDocument();
  });

  it("os cards rotulam o modo, o filtro separa os modos e a comparação só oferece o mesmo modo", async () => {
    stubRecorded([TOOLS_RUN, AGENT_NEW]);
    renderLoad();
    await screen.findByLabelText("Resumo da carga");

    const [agentCard, toolsCard] = within(screen.getByRole("list", { name: "Cargas gravadas" })).getAllByRole("listitem");
    expect(within(agentCard).getByText("Agente · claude")).toBeInTheDocument();
    expect(within(agentCard).getByText(/2 sessões · 120 s · 1\.3 casos\/min/)).toBeInTheDocument();
    expect(within(agentCard).getByText("80%")).toBeInTheDocument();
    expect(within(agentCard).getByText("aprovação")).toBeInTheDocument();
    expect(within(toolsCard).getByText("Tools")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filtrar por modo"), { target: { value: "tools" } });
    expect(within(screen.getByRole("list", { name: "Cargas gravadas" })).getAllByRole("listitem")).toHaveLength(1);
    expect(within(screen.getByRole("list", { name: "Cargas gravadas" })).getByRole("listitem")).toHaveAttribute("data-load-id", TOOLS_RUN.load_id);

    const compare = screen.getByLabelText("Comparar com");
    expect(within(compare).getAllByRole("option")).toHaveLength(1);
    expect(screen.queryByLabelText("Comparação entre cargas")).not.toBeInTheDocument();
  });

  it("compara com a carga anterior do mesmo modo, ignorando as de tools no meio", async () => {
    const toolsBetween = makeLoadRun({
      load_id: "20261024_103000_abc1234",
      timestamp: "2026-10-24T10:30:00",
    });
    stubRecorded([AGENT_OLD, toolsBetween, AGENT_NEW]);
    renderLoad();

    const comparison = await screen.findByLabelText("Comparação entre cargas");
    expect(within(comparison).getByText("Vazão (casos/min)")).toBeInTheDocument();
    expect(within(comparison).getByText("Aprovação")).toBeInTheDocument();
    expect(within(comparison).getByRole("table", { name: "p95 por caso" })).toBeInTheDocument();
    expect(within(comparison).queryByText(/parâmetros diferentes/)).not.toBeInTheDocument();
  });

  it("avisa quando o provedor ou a seleção diferem", async () => {
    const other = makeAgentLoadRun({
      load_id: "20261024_100000_abc1234",
      timestamp: "2026-10-24T10:00:00",
      config: {
        ...AGENT_NEW.config,
        provider: "kiro-cli",
        selection: { case_id: null, group: null, tags: null },
      },
    });
    stubRecorded([other, AGENT_NEW]);
    renderLoad();

    const comparison = await screen.findByLabelText("Comparação entre cargas");
    expect(within(comparison).getByText(/provedor, seleção de casos/)).toBeInTheDocument();
  });
});

describe("Load e a cópia por sessão (sandbox) dos registros", () => {
  it("agente com sandbox mostra a cópia por sessão; sem o campo, a linha some", async () => {
    stubRecorded([makeAgentLoadRun({ sandbox: makeSandbox() })]);
    const { unmount } = renderLoad();
    const details = await screen.findByLabelText("Detalhes da carga");
    expect(within(details).getByText("Cópia por sessão")).toBeInTheDocument();
    expect(
      within(details).getByText(
        "23.4 MB (subárvores: newave/cobre-caso-reduzido), cópia em ~180 ms (máx 240 ms)",
      ),
    ).toBeInTheDocument();
    unmount();

    stubRecorded([makeAgentLoadRun()]);
    renderLoad();
    const old = await screen.findByLabelText("Detalhes da carga");
    expect(within(old).queryByText("Cópia por sessão")).not.toBeInTheDocument();
  });

  it("tools com sandbox mostra a linha; sandbox desligado ou ausente, não", async () => {
    stubRecorded([makeLoadRun({ sandbox: makeSandbox({ copy_ms_max: null }) })]);
    const first = renderLoad();
    const details = await screen.findByLabelText("Detalhes da carga");
    expect(within(details).getByText("Cópia por sessão")).toBeInTheDocument();
    expect(within(details).getByText(/cópia em ~180 ms$/)).toBeInTheDocument();
    first.unmount();

    stubRecorded([makeLoadRun({ sandbox: { enabled: false } })]);
    const second = renderLoad();
    expect(within(await screen.findByLabelText("Detalhes da carga")).queryByText("Cópia por sessão")).not.toBeInTheDocument();
    second.unmount();

    stubRecorded([makeLoadRun()]);
    renderLoad();
    expect(within(await screen.findByLabelText("Detalhes da carga")).queryByText("Cópia por sessão")).not.toBeInTheDocument();
  });

  it("sandbox ativado sem números ainda renderiza ('ativada')", async () => {
    stubRecorded([makeLoadRun({ sandbox: { enabled: true } })]);
    renderLoad();
    const details = await screen.findByLabelText("Detalhes da carga");
    expect(within(details).getByText("ativada")).toBeInTheDocument();
  });
});
