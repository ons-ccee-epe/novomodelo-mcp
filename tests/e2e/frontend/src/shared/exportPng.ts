const SVG_NS = "http://www.w3.org/2000/svg";
const VAR_PATTERN = /var\((--[\w-]+)\)/g;
const FALLBACK_SIZE_PX = 300;

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function svgSize(svg: SVGSVGElement): { width: number; height: number } {
  const rect = svg.getBoundingClientRect();
  const width = Number(svg.getAttribute("width")) || rect.width || FALLBACK_SIZE_PX;
  const height = Number(svg.getAttribute("height")) || rect.height || FALLBACK_SIZE_PX;
  return { width, height };
}

function serialize(svg: SVGSVGElement): { markup: string; width: number; height: number } {
  const { width, height } = svgSize(svg);
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", SVG_NS);
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  const raw = new XMLSerializer().serializeToString(clone);
  return { markup: raw.replace(VAR_PATTERN, (m, name: string) => cssVar(name) || m), width, height };
}

function loadImage(markup: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Falha ao rasterizar o gráfico"));
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
  });
}

function canvasContext(width: number, height: number, scale: number) {
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(width * scale);
  canvas.height = Math.ceil(height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas indisponível");
  ctx.scale(scale, scale);
  ctx.fillStyle = cssVar("--cobre-surface") || "#ffffff";
  ctx.fillRect(0, 0, width, height);
  return { canvas, ctx };
}

function toBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Falha ao gerar o PNG"))), "image/png");
  });
}

export async function svgToPngBlob(svg: SVGSVGElement, scale = 2): Promise<Blob> {
  const { markup, width, height } = serialize(svg);
  const img = await loadImage(markup);
  const { canvas, ctx } = canvasContext(width, height, scale);
  ctx.drawImage(img, 0, 0, width, height);
  return toBlob(canvas);
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const SUMMARY_WIDTH_PX = 1200;
const PAD_PX = 24;
const GAP_PX = 16;
const TITLE_BLOCK_PX = 48;
const CARD_BLOCK_PX = 72;
const COLUMNS = 2;

export async function summaryPngBlob(
  title: string,
  cards: Array<{ label: string; value: string }>,
  svgs: SVGSVGElement[],
  scale = 2,
): Promise<Blob> {
  const colWidth = (SUMMARY_WIDTH_PX - 2 * PAD_PX - GAP_PX) / COLUMNS;
  const loaded = await Promise.all(
    svgs.map(async (svg) => {
      const { markup, width, height } = serialize(svg);
      return { img: await loadImage(markup), drawHeight: (height / width) * colWidth };
    }),
  );
  const rowHeights: number[] = [];
  loaded.forEach((c, i) => {
    const row = Math.floor(i / COLUMNS);
    rowHeights[row] = Math.max(rowHeights[row] ?? 0, c.drawHeight);
  });
  const gridHeight = rowHeights.reduce((sum, h) => sum + h + GAP_PX, 0);
  const totalHeight = PAD_PX + TITLE_BLOCK_PX + CARD_BLOCK_PX + gridHeight + PAD_PX;

  const { canvas, ctx } = canvasContext(SUMMARY_WIDTH_PX, totalHeight, scale);
  const text = cssVar("--cobre-text") || "#1e293b";
  const muted = cssVar("--cobre-text-muted") || "#64748b";
  ctx.textBaseline = "top";
  ctx.fillStyle = text;
  ctx.font = "bold 22px sans-serif";
  ctx.fillText(title, PAD_PX, PAD_PX);

  const cardWidth = cards.length ? (SUMMARY_WIDTH_PX - 2 * PAD_PX) / cards.length : 0;
  cards.forEach((card, i) => {
    const x = PAD_PX + i * cardWidth;
    const y = PAD_PX + TITLE_BLOCK_PX;
    ctx.fillStyle = text;
    ctx.font = "bold 20px sans-serif";
    ctx.fillText(card.value, x, y);
    ctx.fillStyle = muted;
    ctx.font = "12px sans-serif";
    ctx.fillText(card.label, x, y + 28);
  });

  let y = PAD_PX + TITLE_BLOCK_PX + CARD_BLOCK_PX;
  loaded.forEach((c, i) => {
    const col = i % COLUMNS;
    const row = Math.floor(i / COLUMNS);
    if (col === 0 && row > 0) y += rowHeights[row - 1] + GAP_PX;
    ctx.drawImage(c.img, PAD_PX + col * (colWidth + GAP_PX), y, colWidth, c.drawHeight);
  });
  return toBlob(canvas);
}
