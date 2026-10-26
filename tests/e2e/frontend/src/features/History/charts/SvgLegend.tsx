const SWATCH_PX = 10;
const ITEM_GAP_PX = 100;
const PER_ROW = 3;
const ROW_GAP_PX = 16;

export interface LegendItem {
  label: string;
  color: string;
}

export function SvgLegend({ items }: { items: LegendItem[] }) {
  return (
    <g>
      {items.map((item, i) => (
        <g key={item.label} transform={`translate(${8 + (i % PER_ROW) * ITEM_GAP_PX}, ${4 + Math.floor(i / PER_ROW) * ROW_GAP_PX})`}>
          <rect width={SWATCH_PX} height={SWATCH_PX} fill={item.color} />
          <text x={SWATCH_PX + 4} y={SWATCH_PX} fontSize={10} fill="var(--cobre-text)">
            {item.label}
          </text>
        </g>
      ))}
    </g>
  );
}
