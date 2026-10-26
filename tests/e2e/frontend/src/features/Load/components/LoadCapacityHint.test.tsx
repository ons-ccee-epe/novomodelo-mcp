import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeCapacity } from "../fixtures";
import { LoadCapacityHint } from "./LoadCapacityHint";

describe("LoadCapacityHint", () => {
  it("seleção leve e só leitura: sem disco, sem selos, com o custo por RAM e núcleos", () => {
    render(<LoadCapacityHint capacity={makeCapacity()} error={null} />);
    const hint = screen.getByLabelText("Capacidade da máquina");
    expect(hint).toHaveTextContent("Recomendado: ≈ 6 (CPU)");
    expect(hint).toHaveTextContent("Custo por sessão (leve): 200 MB de RAM · 1 núcleo(s) · estimativa");
    expect(hint).not.toHaveTextContent("disco");
    expect(screen.queryByLabelText("Custo da seleção")).not.toBeInTheDocument();
  });

  it("seleção pesada que grava: fator disco, custo de disco por sessão e a cópia", () => {
    const capacity = makeCapacity({
      recommended: 3,
      limiting_factor: "disco",
      limits: { hard_cap: 32, cpu: 7, memory: 40, disk: 3 },
      explanation: "≈ 3 sessões: limitado por disco (50000 MB livres); custo estimado.",
      per_session: { rss_mb: 500, cpu_cores: 1.5, source: "histórico", runs: 4, profile: "pesada" },
      selection: {
        heavy: true,
        writes: true,
        heavy_tools: ["bridge_check_newave"],
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
    render(<LoadCapacityHint capacity={capacity} error={null} />);
    const hint = screen.getByLabelText("Capacidade da máquina");

    expect(hint).toHaveTextContent("Recomendado: ≈ 3 (disco)");
    expect(hint).toHaveTextContent("Limite por fator: teto do modo 32 · CPU 7 · memória 40 · disco 3");
    expect(hint).toHaveTextContent("limitado por disco (50000 MB livres)");
    expect(hint).toHaveTextContent(
      "Custo por sessão (pesada): 500 MB de RAM · 1.5 núcleo(s) · 46.8 MB de disco (cópia 23.4 MB + folga 23.4 MB) · histórico",
    );
    const selection = screen.getByLabelText("Custo da seleção");
    expect(selection).toHaveTextContent("pesada");
    expect(selection).toHaveTextContent("grava · cópia por sessão");
    expect(selection).toHaveTextContent("Seleção pesada: sobe o bridge ou o solver (bridge_check_newave).");
    expect(selection).toHaveTextContent(
      "Seleção que grava: cada sessão copia 23.4 MB de fixtures (newave/cobre-caso-reduzido).",
    );
  });

  it("seleção só pesada (não grava): mostra a pesada e nada de cópia", () => {
    const capacity = makeCapacity({
      per_session: { rss_mb: 500, cpu_cores: 1.5, source: "estimativa", runs: 0, profile: "pesada" },
      selection: {
        heavy: true,
        writes: false,
        heavy_tools: ["run_plan"],
        write_tools: [],
        copy_mb: 0,
        subtrees: [],
      },
    });
    render(<LoadCapacityHint capacity={capacity} error={null} />);
    const selection = screen.getByLabelText("Custo da seleção");
    expect(selection).toHaveTextContent("Seleção pesada");
    expect(selection).not.toHaveTextContent("Seleção que grava");
  });

  it("launcher antigo (sem selection, disk e profile) continua renderizando", () => {
    const capacity = makeCapacity();
    delete capacity.selection;
    delete capacity.disk;
    delete capacity.per_session.profile;
    delete capacity.limits.disk;
    render(<LoadCapacityHint capacity={capacity} error={null} />);
    expect(screen.getByLabelText("Capacidade da máquina")).toHaveTextContent(
      "Custo por sessão: 200 MB de RAM",
    );
  });

  it("sem capacidade: estima ou mostra o erro", () => {
    const { rerender } = render(<LoadCapacityHint capacity={null} error={null} />);
    expect(screen.getByText(/Estimando a capacidade/)).toBeInTheDocument();
    rerender(<LoadCapacityHint capacity={null} error="HTTP 500" />);
    expect(screen.getByText(/indisponível: HTTP 500/)).toBeInTheDocument();
  });
});
