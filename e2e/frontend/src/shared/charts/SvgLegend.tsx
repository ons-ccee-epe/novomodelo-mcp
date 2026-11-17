const SWATCH_PX = 10;
const ITEM_GAP_PX = 100;
const PER_ROW = 3;
const ROW_GAP_PX = 16;

export interface LegendItem {
  label: string;
  color: string;
}

/** ``perRow`` quebra a legenda em linhas; nos gráficos largos, todos os itens cabem numa só. */
export function SvgLegend({ items, perRow = PER_ROW }: { items: LegendItem[]; perRow?: number }) {
  return (
    <g>
      {items.map((item, i) => (
        <g
          key={item.label}
          transform={`translate(${8 + (i % perRow) * ITEM_GAP_PX}, ${4 + Math.floor(i / perRow) * ROW_GAP_PX})`}
        >
          <rect width={SWATCH_PX} height={SWATCH_PX} fill={item.color} />
          <text x={SWATCH_PX + 4} y={SWATCH_PX} fontSize={10} fill="var(--nm-text)">
            {item.label}
          </text>
        </g>
      ))}
    </g>
  );
}
