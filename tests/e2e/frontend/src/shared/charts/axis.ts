/**
 * Estilo comum de eixos, grade e tooltip: os padrões do Recharts (cinza e branco fixos)
 * somem ou ofuscam no modo escuro.
 */
export const AXIS_TICK = { fontSize: 10, fill: "var(--cobre-chart-axis-text)" };
export const AXIS_LINE = "var(--cobre-chart-axis)";
export const GRID_STROKE = "var(--cobre-chart-grid)";

/** Números do tooltip com no máximo uma casa, no formato brasileiro (98.276,3). */
export function tooltipNumber(value: unknown): string {
  return typeof value === "number"
    ? value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })
    : String(value);
}

/** Props do ``<Tooltip>`` nos gráficos de barras; os de linha trocam só o ``cursor``. */
export const TOOLTIP = {
  contentStyle: {
    background: "var(--cobre-surface)",
    border: "1px solid var(--cobre-border)",
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: "var(--cobre-text)", fontWeight: 600 },
  itemStyle: { color: "var(--cobre-text)" },
  cursor: { fill: "var(--cobre-chart-cursor)" },
  formatter: tooltipNumber,
};

export const LINE_CURSOR = { stroke: "var(--cobre-chart-axis)" };
