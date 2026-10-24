import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { LoadSeriesPoint } from "@/shared/types";
import { LoadCharts, trimPartialTail } from "./LoadCharts";

function point(t: number, calls = 10): LoadSeriesPoint {
  return { t, calls, failed: 0, p50_ms: 30, p95_ms: 80 };
}

describe("trimPartialTail", () => {
  it("descarta o último bucket quando a janela mal o cobre", () => {
    const series = [point(0), point(1), point(2), point(3, 2)];
    expect(trimPartialTail(series, 3.1).map((p) => p.t)).toEqual([0, 1, 2]);
  });

  it("mantém o último bucket quando a janela o cobre por pelo menos meio segundo", () => {
    const series = [point(0), point(1), point(2)];
    expect(trimPartialTail(series, 2.5)).toBe(series);
    expect(trimPartialTail(series, 3)).toBe(series);
  });

  it("nunca esvazia a série", () => {
    const series = [point(0)];
    expect(trimPartialTail(series, 0.1)).toBe(series);
    expect(trimPartialTail([], 5)).toEqual([]);
  });
});

describe("LoadCharts", () => {
  it("sem série mostra o aviso em vez dos gráficos", () => {
    render(<LoadCharts series={[]} />);
    expect(screen.getByText("Sem série temporal para esta carga")).toBeInTheDocument();
  });

  it("com série mostra os dois gráficos", () => {
    render(<LoadCharts series={[point(0), point(1)]} durationSeconds={2} />);
    expect(screen.getByText("Latência no tempo (ms)")).toBeInTheDocument();
    expect(screen.getByText("Vazão no tempo (chamadas/s)")).toBeInTheDocument();
  });
});
