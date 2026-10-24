import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { LoadLimits, LoadToolInfo } from "@/services/loadApi";
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
  { tool: "deck_list", group: "deck", calls: 1, available: true, reason: null },
  { tool: "docs_search", group: "docs", calls: 2, available: true, reason: null },
  {
    tool: "results_query",
    group: "results",
    calls: 0,
    available: false,
    reason: "fonte ausente ou vazia: x",
  },
];

function values(overrides: Partial<LoadFormValues> = {}): LoadFormValues {
  return {
    concurrency: "4",
    duration: "30",
    iterations: "",
    timeout: "60",
    tools: new Set(["deck_list", "docs_search"]),
    ...overrides,
  };
}

describe("parseLoadForm", () => {
  it("com todas as tools disponíveis marcadas envia tools nulo (mix inteiro)", () => {
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
    ["concurrency", "0", /Concorrência/],
    ["concurrency", "33", /Concorrência/],
    ["concurrency", "2.5", /Concorrência/],
    ["concurrency", "", /Concorrência/],
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
    fireEvent.change(screen.getByLabelText(/Concorrência/), { target: { value: "8" } });
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
    fireEvent.change(screen.getByLabelText(/Concorrência/), { target: { value: "99" } });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Concorrência deve ser um inteiro de 1 a 32",
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

  it("enquanto há uma carga em andamento os controles ficam desabilitados", () => {
    render(<LoadForm tools={TOOLS} limits={LIMITS} disabled onStart={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Iniciar carga/ })).toBeDisabled();
    expect(screen.getByLabelText(/Concorrência/)).toBeDisabled();
  });
});
