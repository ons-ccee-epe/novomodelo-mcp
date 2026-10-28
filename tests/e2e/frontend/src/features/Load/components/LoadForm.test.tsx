import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { LoadLimits, LoadToolInfo } from "@/services/loadApi";
import { toolInfo } from "../fixtures";
import { LoadForm, parseLoadForm, type LoadFormValues } from "./LoadForm";

const LIMITS: LoadLimits = {
  min_concurrency: 1,
  max_concurrency: 32,
  min_duration_seconds: 1,
  max_duration_seconds: 1800,
  max_iterations: 1_000_000,
  max_timeout_seconds: 1800,
  default_timeout_seconds: 60,
};

const TOOLS: LoadToolInfo[] = [
  toolInfo({ tool: "deck_list", group: "deck", calls: 1 }),
  toolInfo({ tool: "docs_search", group: "docs", calls: 2 }),
  toolInfo({ tool: "deck_edit_json", group: "deck", calls: 1, writes: true, default: false }),
  toolInfo({ tool: "bridge_check_newave", group: "bridge", calls: 1, heavy: true, default: false }),
  toolInfo({
    tool: "bridge_convert_newave",
    group: "bridge",
    calls: 1,
    writes: true,
    heavy: true,
    default: false,
  }),
  toolInfo({
    tool: "results_query",
    group: "results",
    calls: 0,
    available: false,
    reason: "fonte ausente ou vazia: x",
  }),
  toolInfo({
    tool: "run_start",
    group: "run",
    calls: 0,
    available: false,
    barred: true,
    default: false,
    reason: "dispara o solver sem limite de tempo",
  }),
];

const DEFAULT_MIX = ["deck_list", "docs_search"];
const ALL_AVAILABLE = [
  "deck_list",
  "docs_search",
  "deck_edit_json",
  "bridge_check_newave",
  "bridge_convert_newave",
];

function values(overrides: Partial<LoadFormValues> = {}): LoadFormValues {
  return {
    concurrency: "4",
    duration: "30",
    iterations: "",
    timeout: "60",
    tools: new Set(DEFAULT_MIX),
    ...overrides,
  };
}

describe("parseLoadForm", () => {
  it("com exatamente o mix padrão marcado envia tools nulo", () => {
    const parsed = parseLoadForm(values(), LIMITS, TOOLS);
    expect(parsed.errors).toEqual([]);
    expect(parsed.body).toEqual({
      concurrency: 4,
      duration_seconds: 30,
      iterations: null,
      tools: null,
      timeout_seconds: 60,
    });
  });

  it("com todas as disponíveis (inclusive pesadas e que gravam) envia a lista explícita", () => {
    const parsed = parseLoadForm(values({ tools: new Set(ALL_AVAILABLE) }), LIMITS, TOOLS);
    expect(parsed.errors).toEqual([]);
    expect(parsed.body?.tools).toEqual(ALL_AVAILABLE);
  });

  it("o mix padrão mais uma tool que grava vira lista explícita", () => {
    const parsed = parseLoadForm(
      values({ tools: new Set([...DEFAULT_MIX, "deck_edit_json"]) }),
      LIMITS,
      TOOLS,
    );
    expect(parsed.body?.tools).toEqual(["deck_list", "docs_search", "deck_edit_json"]);
  });

  it("só pesadas, sem nenhuma do padrão, também manda a lista", () => {
    const parsed = parseLoadForm(values({ tools: new Set(["bridge_check_newave"]) }), LIMITS, TOOLS);
    expect(parsed.body?.tools).toEqual(["bridge_check_newave"]);
  });

  it("com um subconjunto envia a lista", () => {
    const parsed = parseLoadForm(values({ tools: new Set(["docs_search"]) }), LIMITS, TOOLS);
    expect(parsed.body?.tools).toEqual(["docs_search"]);
  });

  it("ignora uma tool marcada que não está disponível", () => {
    const parsed = parseLoadForm(values({ tools: new Set(["results_query"]) }), LIMITS, TOOLS);
    expect(parsed.body).toBeNull();
    expect(parsed.errors).toContain("Escolha ao menos uma tool.");
  });

  it.each([
    ["concurrency", "0", /Sessões simultâneas/],
    ["concurrency", "33", /Sessões simultâneas/],
    ["concurrency", "2.5", /Sessões simultâneas/],
    ["concurrency", "", /Sessões simultâneas/],
    ["duration", "0", /Duração/],
    ["duration", "1801", /Duração/],
    ["iterations", "0", /Iterações/],
    ["iterations", "1.5", /Iterações/],
    ["timeout", "0", /Timeout/],
    ["timeout", "1801", /Timeout/],
  ])("%s = %s é recusado", (field, raw, message) => {
    const parsed = parseLoadForm(values({ [field]: raw }), LIMITS, TOOLS);
    expect(parsed.body).toBeNull();
    expect(parsed.errors.join(" ")).toMatch(message);
  });

  it("aceita os limites inclusivos", () => {
    const parsed = parseLoadForm(
      values({ concurrency: "32", duration: "1800", timeout: "1800" }),
      LIMITS,
      TOOLS,
    );
    expect(parsed.errors).toEqual([]);
  });
});

describe("LoadForm", () => {
  it("envia o corpo ao iniciar", () => {
    const onStart = vi.fn();
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={onStart} />);
    fireEvent.change(screen.getByLabelText(/Sessões simultâneas/), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText(/Duração/), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));

    expect(onStart).toHaveBeenCalledWith({
      concurrency: 8,
      duration_seconds: 20,
      iterations: null,
      tools: null,
      timeout_seconds: 60,
    });
  });

  it("concorrência fora do limite mostra o erro e bloqueia o início", () => {
    const onStart = vi.fn();
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={onStart} />);
    fireEvent.change(screen.getByLabelText(/Sessões simultâneas/), { target: { value: "99" } });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Sessões simultâneas deve ser um inteiro de 1 a 32",
    );
    const start = screen.getByRole("button", { name: /Iniciar carga/ });
    expect(start).toBeDisabled();
    fireEvent.click(start);
    expect(onStart).not.toHaveBeenCalled();
  });

  it("tool sem fonte aparece desabilitada com o motivo", () => {
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={vi.fn()} />);
    const checkbox = screen.getByRole("checkbox", { name: "results_query" });
    expect(checkbox).toBeDisabled();
    expect(checkbox.closest("label")).toHaveAttribute("title", "fonte ausente ou vazia: x");
  });

  it("desmarcar tools envia só as escolhidas", () => {
    const onStart = vi.fn();
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={onStart} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "deck_list" }));
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    expect(onStart.mock.calls[0][0].tools).toEqual(["docs_search"]);
  });

  it("a seleção inicial é o mix padrão: pesadas e que gravam começam desmarcadas", () => {
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={vi.fn()} />);
    expect(screen.getByRole("checkbox", { name: "deck_list" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "docs_search" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "deck_edit_json" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "bridge_check_newave" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "bridge_convert_newave" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "bridge_convert_newave" })).toBeEnabled();
  });

  it("mostra os selos: grava, pesada ou os dois; as leves não têm selo", () => {
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={vi.fn()} />);
    const slot = (name: string) =>
      screen.getByRole("checkbox", { name }).closest(".nm-load-tool") as HTMLElement;

    expect(within(slot("deck_edit_json")).getByText("grava · cópia por sessão")).toBeInTheDocument();
    expect(within(slot("deck_edit_json")).queryByText("pesada")).not.toBeInTheDocument();
    expect(within(slot("bridge_check_newave")).getByText("pesada")).toBeInTheDocument();
    expect(
      within(slot("bridge_check_newave")).queryByText("grava · cópia por sessão"),
    ).not.toBeInTheDocument();
    expect(within(slot("bridge_convert_newave")).getByText("pesada")).toBeInTheDocument();
    expect(
      within(slot("bridge_convert_newave")).getByText("grava · cópia por sessão"),
    ).toBeInTheDocument();
    expect(slot("deck_list").querySelector(".nm-load-badge")).toBeNull();
  });

  it("a legenda não diz mais que o mix é somente leitura", () => {
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={vi.fn()} />);
    expect(screen.getByText(/Tools do mix/)).toBeInTheDocument();
    expect(screen.queryByText(/somente leitura/)).not.toBeInTheDocument();
  });

  it('"todas" marca todas as disponíveis e manda a lista explícita; "nenhuma" limpa', () => {
    const onStart = vi.fn();
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={onStart} />);
    fireEvent.click(screen.getByRole("button", { name: "todas" }));
    expect(screen.getByRole("checkbox", { name: "bridge_check_newave" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "results_query" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    expect(onStart.mock.calls[0][0].tools).toEqual(ALL_AVAILABLE);

    fireEvent.click(screen.getByRole("button", { name: "nenhuma" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Escolha ao menos uma tool.");
    expect(screen.getByRole("button", { name: /Iniciar carga/ })).toBeDisabled();
  });

  it("marcar uma tool que grava sai do mix padrão e manda a lista", () => {
    const onStart = vi.fn();
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={onStart} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "deck_edit_json" }));
    fireEvent.click(screen.getByRole("button", { name: /Iniciar carga/ }));
    expect(onStart.mock.calls[0][0].tools).toEqual(["deck_list", "docs_search", "deck_edit_json"]);
  });

  it("as barradas ficam numa lista 'Fora da carga' com o motivo, sem checkbox", () => {
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled={false} onStart={vi.fn()} />);
    expect(screen.queryByRole("checkbox", { name: "run_start" })).not.toBeInTheDocument();
    const details = screen.getByText("Fora da carga (1)").closest("details");
    expect(details).toHaveTextContent("run_start");
    expect(details).toHaveTextContent("dispara o solver sem limite de tempo");
  });

  it("enquanto há uma carga em andamento os controles ficam desabilitados", () => {
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled onStart={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Iniciar carga/ })).toBeDisabled();
    expect(screen.getByLabelText(/Sessões simultâneas/)).toBeDisabled();
  });
});

describe("LoadForm pede a capacidade com a seleção", () => {
  function renderWithCapacity() {
    const onRequestCapacity = vi.fn();
    render(
      <LoadForm
        tools={TOOLS}
        limits={LIMITS}
        disabled={false}
        onStart={vi.fn()}
        onRequestCapacity={onRequestCapacity}
      />,
    );
    return onRequestCapacity;
  }

  it("modo tools: mix padrão = tools nulo; cada mudança refaz o pedido com a lista", () => {
    const onRequestCapacity = renderWithCapacity();
    expect(onRequestCapacity).toHaveBeenCalledTimes(1);
    expect(onRequestCapacity).toHaveBeenLastCalledWith("tools", null, { tools: null });

    fireEvent.click(screen.getByRole("checkbox", { name: "bridge_check_newave" }));
    expect(onRequestCapacity).toHaveBeenCalledTimes(2);
    expect(onRequestCapacity).toHaveBeenLastCalledWith("tools", null, {
      tools: ["deck_list", "docs_search", "bridge_check_newave"],
    });

    // Desmarcar de volta = mix padrão de novo.
    fireEvent.click(screen.getByRole("checkbox", { name: "bridge_check_newave" }));
    expect(onRequestCapacity).toHaveBeenLastCalledWith("tools", null, { tools: null });

    fireEvent.click(screen.getByRole("button", { name: "todas" }));
    expect(onRequestCapacity).toHaveBeenLastCalledWith("tools", null, { tools: ALL_AVAILABLE });
  });

  it("mudar outro campo (sessões) não refaz o pedido", () => {
    const onRequestCapacity = renderWithCapacity();
    fireEvent.change(screen.getByLabelText(/Sessões simultâneas/), { target: { value: "5" } });
    expect(onRequestCapacity).toHaveBeenCalledTimes(1);
  });
});
