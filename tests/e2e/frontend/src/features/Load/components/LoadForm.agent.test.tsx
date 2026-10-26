import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ProviderInfo } from "@/services/launcherApi";
import type {
  AgentCatalog,
  LoadCapacity,
  LoadCaseInfo,
  LoadLimits,
  LoadToolInfo,
} from "@/services/loadApi";
import { caseInfo as makeCaseInfo, makeCapacity, toolInfo } from "../fixtures";
import { LoadForm, parseLoadForm, type LoadFormValues } from "./LoadForm";

const TOOLS_LIMITS: LoadLimits = {
  min_concurrency: 1,
  max_concurrency: 32,
  min_duration_seconds: 1,
  max_duration_seconds: 1800,
  max_iterations: 1_000_000,
  max_timeout_seconds: 1800,
  default_timeout_seconds: 60,
};

const AGENT_LIMITS: LoadLimits = { ...TOOLS_LIMITS, max_concurrency: 8, default_timeout_seconds: null };

const TOOLS: LoadToolInfo[] = [
  toolInfo({ tool: "deck_list", group: "deck", calls: 1 }),
  toolInfo({ tool: "docs_search", group: "docs", calls: 2 }),
];

function caseInfo(overrides: Partial<LoadCaseInfo>): LoadCaseInfo {
  return makeCaseInfo(overrides);
}

const PROVIDERS: ProviderInfo[] = [
  { id: "kiro-cli", label: "Kiro CLI", binary: "kiro-cli", installed: false },
  { id: "claude", label: "Claude Code", binary: "claude", installed: true },
];

const AGENT: AgentCatalog = {
  limits: AGENT_LIMITS,
  providers: PROVIDERS,
  defaultProvider: "claude",
  cases: [
    caseInfo({ id: "docs_search#a", query: "busque a metodologia" }),
    caseInfo({ id: "docs_list#b", expected_tool: "docs_list", query: "liste as docs" }),
    caseInfo({ id: "deck_list#c", group: "deck", expected_tool: "deck_list", query: "liste decks" }),
    caseInfo({
      id: "run_start#x",
      group: "run",
      expected_tool: "run_start",
      available: false,
      reason: "dispara o solver",
    }),
  ],
};

const CAPACITY: LoadCapacity = {
  mode: "agent",
  provider: "claude",
  hard_cap: 8,
  recommended: 2,
  limiting_factor: "memória",
  limits: { hard_cap: 8, cpu: 6, memory: 2 },
  explanation:
    "≈ 2 sessões: limitado por memória (2303 MB livres × 75% ÷ 600 MB/sessão, folga de 25%); custo por sessão estimado, sem histórico.",
  cpu: { logical_cores: 8, reserved_cores: 2 },
  memory: { total_mb: 16000, available_mb: 2303 },
  per_session: { rss_mb: 600, cpu_cores: 0.5, source: "estimativa", runs: 0 },
  memory_headroom: 0.25,
  warnings: ["Pouca memória livre: feche outros programas."],
};

function values(overrides: Partial<LoadFormValues> = {}): LoadFormValues {
  return {
    mode: "agent",
    concurrency: "2",
    duration: "30",
    iterations: "",
    timeout: "",
    tools: new Set(),
    provider: "claude",
    ...overrides,
  };
}

function renderForm(props: Partial<ComponentProps<typeof LoadForm>> = {}) {
  const onStart = vi.fn();
  render(
    <LoadForm
      tools={TOOLS}
      limits={TOOLS_LIMITS}
      disabled={false}
      onStart={onStart}
      agent={AGENT}
      {...props}
    />,
  );
  return onStart;
}

function switchToAgent() {
  fireEvent.change(screen.getByLabelText("Modo"), { target: { value: "agent" } });
}

describe("parseLoadForm no modo agente", () => {
  const ctx = { agent: AGENT };

  it("todos os casos: corpo só com os campos do agente", () => {
    const parsed = parseLoadForm(values(), TOOLS_LIMITS, TOOLS, ctx);
    expect(parsed.errors).toEqual([]);
    expect(parsed.body).toEqual({
      mode: "agent",
      concurrency: 2,
      duration_seconds: 30,
      iterations: null,
      timeout_seconds: null,
      provider: "claude",
    });
    expect(parsed.body).not.toHaveProperty("tools");
  });

  it("grupo e caso entram no corpo", () => {
    expect(parseLoadForm(values({ scope: "group", group: "docs" }), TOOLS_LIMITS, TOOLS, ctx).body)
      .toMatchObject({ group: "docs" });
    expect(
      parseLoadForm(values({ scope: "case", caseId: "deck_list#c" }), TOOLS_LIMITS, TOOLS, ctx).body,
    ).toMatchObject({ case_id: "deck_list#c" });
  });

  it("usa o teto do agente, não o das tools", () => {
    const parsed = parseLoadForm(values({ concurrency: "9" }), TOOLS_LIMITS, TOOLS, ctx);
    expect(parsed.body).toBeNull();
    expect(parsed.errors.join(" ")).toMatch(/Sessões simultâneas deve ser um inteiro de 1 a 8/);
  });

  it.each([
    ["grupo sem escolha", { scope: "group" as const, group: null }, /Escolha um grupo/],
    ["grupo sem elegíveis", { scope: "group" as const, group: "run" }, /não tem casos elegíveis/],
    ["caso inelegível", { scope: "case" as const, caseId: "run_start#x" }, /Escolha um caso/],
    ["provedor ausente", { provider: null }, /Nenhum provedor/],
    ["provedor não instalado", { provider: "kiro-cli" as const }, /Nenhum provedor/],
  ])("%s é recusado", (_name, overrides, message) => {
    const parsed = parseLoadForm(values(overrides), TOOLS_LIMITS, TOOLS, ctx);
    expect(parsed.body).toBeNull();
    expect(parsed.errors.join(" ")).toMatch(message);
  });

  it("acima do recomendado só avisa; acima do teto bloqueia", () => {
    const warned = parseLoadForm(values({ concurrency: "5" }), TOOLS_LIMITS, TOOLS, {
      agent: AGENT,
      capacity: CAPACITY,
    });
    expect(warned.errors).toEqual([]);
    expect(warned.body).not.toBeNull();
    expect(warned.warnings.join(" ")).toMatch(/Acima do recomendado \(≈ 2\)/);

    const blocked = parseLoadForm(values({ concurrency: "9" }), TOOLS_LIMITS, TOOLS, {
      agent: AGENT,
      capacity: CAPACITY,
    });
    expect(blocked.body).toBeNull();
    expect(blocked.warnings).toEqual([]);
  });
});

describe("LoadForm com o modo agente", () => {
  it("começa em tools e a troca de modo mostra provedor, casos e o aviso de tokens", () => {
    renderForm();
    expect(screen.getByRole("checkbox", { name: "deck_list" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Provedor de IA")).not.toBeInTheDocument();

    switchToAgent();

    expect(screen.queryByRole("checkbox", { name: "deck_list" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Provedor de IA")).toBeInTheDocument();
    expect(screen.getByLabelText("Timeout por caso (s, opcional)")).toHaveValue(null);
    expect(screen.getByText(/consome tokens do provedor \(Claude Code\)/)).toBeInTheDocument();
    expect(screen.getByText(/limitado pela duração/)).toBeInTheDocument();
  });

  it("com iterações o aviso mostra o máximo de execuções", () => {
    renderForm();
    switchToAgent();
    fireEvent.change(screen.getByLabelText(/Sessões simultâneas/), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText(/Iterações por sessão/), { target: { value: "3" } });
    expect(screen.getByText(/até 4 × 3 = 12 execuções/)).toBeInTheDocument();
  });

  it("provedor não instalado fica desabilitado e o padrão é o do launcher", () => {
    renderForm();
    switchToAgent();
    const select = screen.getByLabelText("Provedor de IA") as HTMLSelectElement;
    expect(select.value).toBe("claude");
    expect(screen.getByRole("option", { name: "Kiro CLI (não instalado)" })).toBeDisabled();
  });

  it("todos os casos: dispara com os campos do agente", () => {
    const onStart = renderForm();
    switchToAgent();
    expect(screen.getByLabelText(/Todos os casos \(3 elegíveis\)/)).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    expect(onStart).toHaveBeenCalledWith({
      mode: "agent",
      concurrency: 2,
      duration_seconds: 30,
      iterations: null,
      timeout_seconds: null,
      provider: "claude",
    });
  });

  it("grupo: mostra elegíveis/total, desabilita grupo sem elegíveis e envia o grupo", () => {
    const onStart = renderForm();
    switchToAgent();
    fireEvent.click(screen.getByLabelText("Grupo", { selector: "input" }));

    expect(screen.getByRole("button", { name: /Iniciar carga/ })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Escolha um grupo.");
    expect(screen.getByRole("option", { name: "docs (2/2 elegíveis)" })).toBeEnabled();
    expect(screen.getByRole("option", { name: "run (0/1 elegíveis)" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Grupo", { selector: "select" }), {
      target: { value: "docs" },
    });
    fireEvent.change(screen.getByLabelText("Timeout por caso (s, opcional)"), {
      target: { value: "45" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    expect(onStart).toHaveBeenCalledWith({
      mode: "agent",
      concurrency: 2,
      duration_seconds: 30,
      iterations: null,
      timeout_seconds: 45,
      provider: "claude",
      group: "docs",
    });
  });

  it("um caso: lista só os elegíveis, filtra por grupo e envia o case_id", () => {
    const onStart = renderForm();
    switchToAgent();
    fireEvent.click(screen.getByLabelText("Um caso"));

    const list = screen.getByRole("complementary", { name: "Testes" });
    expect(within(list).queryByText("run_start#x")).not.toBeInTheDocument();
    expect(within(list).getAllByRole("button")).toHaveLength(3);

    fireEvent.change(screen.getByLabelText("Filtrar por grupo"), { target: { value: "deck" } });
    expect(within(list).getAllByRole("button")).toHaveLength(1);

    expect(screen.getByRole("button", { name: /Iniciar carga/ })).toBeDisabled();
    fireEvent.click(within(list).getByRole("button", { name: /deck_list#c/ }));
    expect(screen.getByLabelText("Caso escolhido")).toHaveTextContent("liste decks");

    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    expect(onStart.mock.calls[0][0]).toMatchObject({ mode: "agent", case_id: "deck_list#c" });
    expect(onStart.mock.calls[0][0]).not.toHaveProperty("group");
  });

  it("lista os casos fora da carga com o motivo", () => {
    renderForm();
    switchToAgent();
    const details = screen.getByText("Fora da carga (1)").closest("details");
    expect(details).toHaveTextContent("run_start#x");
    expect(details).toHaveTextContent("dispara o solver");
  });

  it("sem o catálogo do agente, o modo fica indisponível e explica o motivo", () => {
    renderForm({ agent: null, agentError: "HTTP 404" });
    expect(screen.getByRole("option", { name: "Casos por agente" })).toBeDisabled();
    expect(screen.getByText(/Modo agente indisponível: HTTP 404/)).toBeInTheDocument();
  });
});

describe("LoadForm e a capacidade da máquina", () => {
  it("pede a capacidade ao montar e de novo ao trocar de modo", () => {
    const onRequestCapacity = vi.fn();
    renderForm({ onRequestCapacity });
    expect(onRequestCapacity).toHaveBeenLastCalledWith("tools", null, { tools: null });
    switchToAgent();
    expect(onRequestCapacity).toHaveBeenLastCalledWith("agent", "claude", {});
  });

  it("agente: refaz o pedido com o grupo ou o caso escolhido (um só)", () => {
    const onRequestCapacity = vi.fn();
    renderForm({ onRequestCapacity });
    switchToAgent();

    fireEvent.click(screen.getByLabelText("Grupo", { selector: "input" }));
    expect(onRequestCapacity).toHaveBeenLastCalledWith("agent", "claude", { group: null });
    fireEvent.change(screen.getByLabelText("Grupo", { selector: "select" }), {
      target: { value: "docs" },
    });
    expect(onRequestCapacity).toHaveBeenLastCalledWith("agent", "claude", { group: "docs" });

    fireEvent.click(screen.getByLabelText("Um caso"));
    const list = screen.getByRole("complementary", { name: "Testes" });
    fireEvent.click(within(list).getByRole("button", { name: /deck_list#c/ }));
    expect(onRequestCapacity).toHaveBeenLastCalledWith("agent", "claude", { caseId: "deck_list#c" });

    fireEvent.click(screen.getByLabelText(/Todos os casos/));
    expect(onRequestCapacity).toHaveBeenLastCalledWith("agent", "claude", {});
  });

  it("mostra recomendação, explicação e avisos; o input usa o teto do modo", () => {
    renderForm({ capacity: CAPACITY, onRequestCapacity: vi.fn() });
    switchToAgent();

    const hint = screen.getByLabelText("Capacidade da máquina");
    expect(hint).toHaveTextContent("Recomendado: ≈ 2 (memória)");
    expect(hint).toHaveTextContent("2303 MB livres × 75% ÷ 600 MB/sessão");
    expect(hint).toHaveTextContent("Pouca memória livre");
    expect(screen.getByLabelText(/Sessões simultâneas/)).toHaveAttribute("max", "8");
  });

  it("a capacidade de outro modo não aparece", () => {
    renderForm({ capacity: CAPACITY, onRequestCapacity: vi.fn() });
    expect(screen.queryByLabelText("Capacidade da máquina")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Sessões simultâneas/)).toHaveAttribute("max", "32");
  });

  it("acima do teto rígido bloqueia o envio", () => {
    const onStart = renderForm({ capacity: CAPACITY, onRequestCapacity: vi.fn() });
    switchToAgent();
    fireEvent.change(screen.getByLabelText(/Sessões simultâneas/), { target: { value: "9" } });

    expect(screen.getByRole("alert")).toHaveTextContent("de 1 a 8");
    const start = screen.getByRole("button", { name: /Iniciar carga/ });
    expect(start).toBeDisabled();
    fireEvent.click(start);
    expect(onStart).not.toHaveBeenCalled();
  });

  it("acima do recomendado avisa, mas não bloqueia", () => {
    const onStart = renderForm({ capacity: CAPACITY, onRequestCapacity: vi.fn() });
    switchToAgent();
    fireEvent.change(screen.getByLabelText(/Sessões simultâneas/), { target: { value: "5" } });

    expect(screen.getByText(/Acima do recomendado \(≈ 2\)/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    expect(onStart).toHaveBeenCalledOnce();
    expect(onStart.mock.calls[0][0].concurrency).toBe(5);
  });

  it("sem capacidade carregada só o teto vale", () => {
    renderForm({ capacityError: "HTTP 500", onRequestCapacity: vi.fn() });
    expect(screen.getByText(/Capacidade da máquina indisponível: HTTP 500/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Sessões simultâneas/), { target: { value: "30" } });
    expect(screen.getByRole("button", { name: /Iniciar carga/ })).toBeEnabled();
  });
});

describe("LoadForm com casos que gravam e pesados", () => {
  const WEIGHTED: AgentCatalog = {
    ...AGENT,
    cases: [
      caseInfo({ id: "docs_search#a", query: "busque" }),
      caseInfo({
        id: "deck_edit#w",
        group: "deck",
        expected_tool: "deck_edit_json",
        writes: true,
        query: "edite",
      }),
      caseInfo({
        id: "bridge#h",
        group: "deck",
        expected_tool: "bridge_convert_newave",
        writes: true,
        heavy: true,
        query: "converta",
      }),
      caseInfo({ id: "run_plan#p", group: "run", expected_tool: "run_plan", heavy: true, query: "planeje" }),
      caseInfo({
        id: "run_start#x",
        group: "run",
        expected_tool: "run_start",
        available: false,
        writes: true,
        heavy: true,
        reason: "dispara o solver",
      }),
    ],
  };

  it("'Todos os casos' conta elegíveis, os que gravam e os pesados (só os elegíveis)", () => {
    renderForm({ agent: WEIGHTED });
    switchToAgent();
    expect(
      screen.getByLabelText("Todos os casos (4 elegíveis · 2 gravam · 2 pesados)"),
    ).toBeChecked();
  });

  it("os grupos mostram a contagem só quando há; o sem peso fica como antes", () => {
    renderForm({ agent: WEIGHTED });
    switchToAgent();
    fireEvent.click(screen.getByLabelText("Grupo", { selector: "input" }));
    expect(screen.getByRole("option", { name: "docs (1/1 elegíveis)" })).toBeEnabled();
    expect(
      screen.getByRole("option", { name: "deck (2/2 elegíveis · 2 gravam · 1 pesado)" }),
    ).toBeEnabled();
    expect(screen.getByRole("option", { name: "run (1/2 elegíveis · 1 pesado)" })).toBeEnabled();
  });

  it("o resumo do caso escolhido mostra os selos", () => {
    renderForm({ agent: WEIGHTED });
    switchToAgent();
    fireEvent.click(screen.getByLabelText("Um caso"));
    const list = screen.getByRole("complementary", { name: "Testes" });

    fireEvent.click(within(list).getByRole("button", { name: /bridge#h/ }));
    let summary = screen.getByLabelText("Caso escolhido");
    expect(within(summary).getByText("grava · cópia por sessão")).toBeInTheDocument();
    expect(within(summary).getByText("pesada")).toBeInTheDocument();

    fireEvent.click(within(list).getByRole("button", { name: /docs_search#a/ }));
    summary = screen.getByLabelText("Caso escolhido");
    expect(within(summary).queryByText("pesada")).not.toBeInTheDocument();
    expect(within(summary).queryByText("grava · cópia por sessão")).not.toBeInTheDocument();
  });

  it("a lista 'Fora da carga' continua com o motivo do backend", () => {
    renderForm({ agent: WEIGHTED });
    switchToAgent();
    expect(screen.getByText("Fora da carga (1)").closest("details")).toHaveTextContent(
      "dispara o solver",
    );
  });

  it("a dica de capacidade mostra o fator disco e a seleção pesada que grava", () => {
    const capacity = makeCapacity({
      mode: "agent",
      provider: "claude",
      hard_cap: 8,
      recommended: 3,
      limiting_factor: "disco",
      limits: { hard_cap: 8, cpu: 7, memory: 40, disk: 3 },
      per_session: { rss_mb: 500, cpu_cores: 1.5, source: "estimativa", runs: 0, profile: "pesada" },
      selection: {
        heavy: true,
        writes: true,
        heavy_tools: ["bridge_convert_newave"],
        write_tools: ["deck_edit_json"],
        copy_mb: 23.4,
        subtrees: ["newave/cobre-caso-reduzido"],
      },
      disk: {
        path: "C:\\Temp",
        free_mb: 50000,
        copy_mb: 23.4,
        growth: 1,
        per_session_mb: 46.8,
        headroom: 0.1,
      },
    });
    renderForm({ agent: WEIGHTED, capacity, onRequestCapacity: vi.fn() });
    switchToAgent();
    const hint = screen.getByLabelText("Capacidade da máquina");
    expect(hint).toHaveTextContent("Recomendado: ≈ 3 (disco)");
    expect(hint).toHaveTextContent("disco 3");
    expect(hint).toHaveTextContent("Seleção pesada");
    expect(hint).toHaveTextContent("Seleção que grava");
  });
});
