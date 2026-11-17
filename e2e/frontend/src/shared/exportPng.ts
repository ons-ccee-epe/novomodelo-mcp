const SVG_NS = "http://www.w3.org/2000/svg";
const VAR_PATTERN = /var\((--[\w-]+)\)/g;
const FALLBACK_SIZE_PX = 300;
const FALLBACK_FONT = "sans-serif";

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** A fonte da página: o SVG serializado perde o CSS e cairia na serifada padrão do navegador. */
function pageFont(): string {
  return getComputedStyle(document.body).fontFamily || FALLBACK_FONT;
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
  clone.setAttribute("font-family", pageFont());
  const raw = new XMLSerializer().serializeToString(clone);
  return {
    markup: raw.replace(VAR_PATTERN, (m, name: string) => cssVar(name) || m),
    width,
    height,
  };
}

function loadImage(markup: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Falha ao rasterizar o gráfico"));
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
  });
}

function canvasContext(width: number, height: number, scale: number, background?: string) {
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(width * scale);
  canvas.height = Math.ceil(height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas indisponível");
  ctx.scale(scale, scale);
  ctx.fillStyle = background || cssVar("--nm-surface") || "#ffffff";
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

/** Um gráfico do resumo: o título do card e se ele ocupa a linha inteira, como na tela. */
export interface SummaryChart {
  title: string;
  svg: SVGSVGElement;
  wide?: boolean;
}

const SUMMARY_WIDTH_PX = 1200;
const PAD_PX = 24;
const GAP_PX = 16;
const TITLE_BLOCK_PX = 48;
const CARD_BLOCK_PX = 72;
const COLUMNS = 2;
const CARDS_PER_ROW = 6;
const CHART_PAD_PX = 14;
const CHART_TITLE_PX = 26;

interface PlacedChart {
  title: string;
  img: HTMLImageElement;
  x: number;
  width: number;
  imgWidth: number;
  imgHeight: number;
}

/**
 * Os gráficos largos ocupam a linha inteira; os demais vão em pares, na ordem da tela. Nenhum
 * passa do tamanho em que foi desenhado: ampliado, o texto dos eixos ficaria desproporcional.
 */
function layoutRows(
  loaded: Array<{
    title: string;
    img: HTMLImageElement;
    width: number;
    height: number;
    wide: boolean;
  }>,
) {
  const inner = SUMMARY_WIDTH_PX - 2 * PAD_PX;
  const half = (inner - GAP_PX) / COLUMNS;
  const rows: PlacedChart[][] = [];
  let pending: PlacedChart[] | null = null;
  for (const c of loaded) {
    const width = c.wide ? inner : half;
    const imgWidth = Math.min(width - 2 * CHART_PAD_PX, c.width);
    const chart = {
      title: c.title,
      img: c.img,
      width,
      x: PAD_PX,
      imgWidth,
      imgHeight: (c.height / c.width) * imgWidth,
    };
    if (c.wide) {
      rows.push([chart]);
      pending = null;
    } else if (pending && pending.length < COLUMNS) {
      chart.x = PAD_PX + half + GAP_PX;
      pending.push(chart);
      pending = null;
    } else {
      pending = [chart];
      rows.push(pending);
    }
  }
  return rows;
}

const rowHeight = (row: PlacedChart[]) =>
  Math.max(...row.map((c) => c.imgHeight)) + CHART_TITLE_PX + 2 * CHART_PAD_PX;

export async function summaryPngBlob(
  title: string,
  cards: Array<{ label: string; value: string }>,
  charts: SummaryChart[],
  scale = 2,
): Promise<Blob> {
  const loaded = await Promise.all(
    charts.map(async (c) => {
      const { markup, width, height } = serialize(c.svg);
      return {
        title: c.title,
        img: await loadImage(markup),
        width,
        height,
        wide: !!c.wide,
      };
    }),
  );
  const rows = layoutRows(loaded);
  const gridHeight = rows.reduce((sum, row) => sum + rowHeight(row) + GAP_PX, 0);
  const cardsHeight = Math.ceil(cards.length / CARDS_PER_ROW) * CARD_BLOCK_PX;
  const totalHeight = PAD_PX + TITLE_BLOCK_PX + cardsHeight + gridHeight + PAD_PX;

  const { canvas, ctx } = canvasContext(
    SUMMARY_WIDTH_PX,
    totalHeight,
    scale,
    cssVar("--nm-bg") || undefined,
  );
  const font = pageFont();
  const text = cssVar("--nm-text") || "#1e293b";
  const muted = cssVar("--nm-text-muted") || "#64748b";
  const surface = cssVar("--nm-surface") || "#ffffff";
  const border = cssVar("--nm-border") || "#e2e8f0";
  ctx.textBaseline = "top";
  ctx.fillStyle = text;
  ctx.font = `bold 22px ${font}`;
  ctx.fillText(title, PAD_PX, PAD_PX);

  const cardWidth = (SUMMARY_WIDTH_PX - 2 * PAD_PX) / CARDS_PER_ROW;
  cards.forEach((card, i) => {
    const x = PAD_PX + (i % CARDS_PER_ROW) * cardWidth;
    const y = PAD_PX + TITLE_BLOCK_PX + Math.floor(i / CARDS_PER_ROW) * CARD_BLOCK_PX;
    ctx.fillStyle = text;
    ctx.font = `bold 20px ${font}`;
    ctx.fillText(card.value, x, y);
    ctx.fillStyle = muted;
    ctx.font = `12px ${font}`;
    ctx.fillText(card.label, x, y + 28);
  });

  let y = PAD_PX + TITLE_BLOCK_PX + cardsHeight;
  for (const row of rows) {
    const height = rowHeight(row);
    for (const c of row) {
      ctx.fillStyle = surface;
      ctx.fillRect(c.x, y, c.width, height);
      ctx.strokeStyle = border;
      ctx.lineWidth = 1;
      ctx.strokeRect(c.x + 0.5, y + 0.5, c.width - 1, height - 1);
      ctx.fillStyle = muted;
      ctx.font = `bold 12px ${font}`;
      ctx.fillText(c.title.toUpperCase(), c.x + CHART_PAD_PX, y + CHART_PAD_PX);
      ctx.drawImage(
        c.img,
        c.x + (c.width - c.imgWidth) / 2,
        y + CHART_PAD_PX + CHART_TITLE_PX,
        c.imgWidth,
        c.imgHeight,
      );
    }
    y += height + GAP_PX;
  }
  return toBlob(canvas);
}
