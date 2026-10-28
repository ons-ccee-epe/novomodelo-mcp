/**
 * Estilo comum de eixos, grade e tooltip: os padrões do Recharts (cinza e branco fixos)
 * somem ou ofuscam no modo escuro.
 */
export const AXIS_TICK = { fontSize: 10, fill: "var(--nm-chart-axis-text)" };
export const AXIS_LINE = "var(--nm-chart-axis)";
export const GRID_STROKE = "var(--nm-chart-grid)";

/** Números do tooltip com no máximo uma casa, no formato brasileiro (98.276,3). */
export function tooltipNumber(value: unknown): string {
  return typeof value === "number"
    ? value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })
    : String(value);
}

/** Props do ``<Tooltip>`` nos gráficos de barras; os de linha trocam só o ``cursor``. */
export const TOOLTIP = {
  contentStyle: {
    background: "var(--nm-surface)",
    border: "1px solid var(--nm-border)",
    borderRadius: 6,
    fontSize: 12,
  },
  labelStyle: { color: "var(--nm-text)", fontWeight: 600 },
  itemStyle: { color: "var(--nm-text)" },
  cursor: { fill: "var(--nm-chart-cursor)" },
  formatter: tooltipNumber,
};

export const LINE_CURSOR = { stroke: "var(--nm-chart-axis)" };
