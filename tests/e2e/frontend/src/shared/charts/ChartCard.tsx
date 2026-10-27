import { useRef, useState, type ReactNode } from "react";

import { downloadBlob, svgToPngBlob } from "@/shared/exportPng";

interface Props {
  title: string;
  fileName: string;
  /** Ocupa a linha inteira da grade (gráficos com uma barra por item). */
  wide?: boolean;
  children: ReactNode;
}

export function chartSvg(root: ParentNode): SVGSVGElement | null {
  return root.querySelector<SVGSVGElement>(".recharts-wrapper > svg") ?? root.querySelector("svg");
}

export function ChartCard({ title, fileName, wide = false, children }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    const svg = bodyRef.current ? chartSvg(bodyRef.current) : null;
    if (!svg) {
      setError("Gráfico indisponível");
      return;
    }
    try {
      setError(null);
      downloadBlob(await svgToPngBlob(svg), fileName);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <figure className="cobre-chart-card" data-chart-card data-wide={wide || undefined}>
      <figcaption className="cobre-chart-card-head">
        <h4 className="cobre-section-title">{title}</h4>
        <button type="button" className="cobre-btn" onClick={download}>
          ⤓ PNG
        </button>
      </figcaption>
      {error && (
        <p role="alert" className="cobre-muted">
          {error}
        </p>
      )}
      <div ref={bodyRef}>{children}</div>
    </figure>
  );
}
