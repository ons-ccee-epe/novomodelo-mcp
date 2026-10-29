import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadBlob, summaryPngBlob, svgToPngBlob } from "./exportPng";

const drawn: string[] = [];

function mockEnv() {
  drawn.length = 0;
  vi.stubGlobal("getComputedStyle", () => ({
    fontFamily: "Segoe UI, sans-serif",
    getPropertyValue: (n: string) => (n === "--nm-pass" ? "#22c55e" : "#ffffff"),
  }));
  const ctx = {
    scale: vi.fn(),
    fillRect: vi.fn(),
    strokeRect: vi.fn(),
    drawImage: vi.fn(),
    fillText: vi.fn((t: string) => drawn.push(t)),
    set fillStyle(_v: string) {},
    set font(_v: string) {},
    set textBaseline(_v: string) {},
    set strokeStyle(_v: string) {},
    set lineWidth(_v: number) {},
  };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    ctx as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((cb) =>
    cb(new Blob(["x"], { type: "image/png" })),
  );
  const sources: string[] = [];
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    width = 100;
    height = 50;
    set src(v: string) {
      sources.push(decodeURIComponent(v));
      queueMicrotask(() => this.onload?.());
    }
  }
  vi.stubGlobal("Image", FakeImage);
  return { ctx, sources };
}

function makeSvg(width = 100): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", "50");
  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("fill", "var(--nm-pass)");
  svg.appendChild(rect);
  return svg;
}

describe("exportPng", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:x"),
      revokeObjectURL: vi.fn(),
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("svgToPngBlob troca var(--nm-*) pela cor computada", async () => {
    const { sources } = mockEnv();
    const blob = await svgToPngBlob(makeSvg());
    expect(blob.type).toBe("image/png");
    expect(sources[0]).toContain("#22c55e");
    expect(sources[0]).not.toContain("var(--nm-pass)");
  });

  it("svgToPngBlob leva a fonte da página para o SVG", async () => {
    const { sources } = mockEnv();
    await svgToPngBlob(makeSvg());
    expect(sources[0]).toContain('font-family="Segoe UI, sans-serif"');
  });

  it("summaryPngBlob escreve título, cards e o título de cada gráfico", async () => {
    mockEnv();
    const blob = await summaryPngBlob(
      "bateria x",
      [{ label: "Total", value: "4" }],
      [{ title: "Status", svg: makeSvg() }],
    );
    expect(blob.type).toBe("image/png");
    expect(drawn).toContain("bateria x");
    expect(drawn).toContain("Total");
    expect(drawn).toContain("4");
    expect(drawn).toContain("STATUS");
  });

  it("summaryPngBlob põe os largos na linha inteira e os demais em pares", async () => {
    const { ctx } = mockEnv();
    await summaryPngBlob(
      "b",
      [],
      [
        { title: "A", svg: makeSvg(2000) },
        { title: "B", svg: makeSvg(2000) },
        { title: "Largo", svg: makeSvg(2000), wide: true },
        { title: "C", svg: makeSvg(2000) },
      ],
      1,
    );
    const calls = ctx.drawImage.mock.calls.map(([, x, y, w]) => ({ x, y, w }));
    expect(calls[0].y).toBe(calls[1].y);
    expect(calls[1].x).toBeGreaterThan(calls[0].x);
    expect(calls[2].w).toBeGreaterThan(calls[0].w * 2);
    expect(calls[3].y).toBeGreaterThan(calls[2].y);
    expect(calls[3].x).toBe(calls[0].x);
  });

  it("summaryPngBlob não amplia um gráfico além do tamanho desenhado", async () => {
    const { ctx } = mockEnv();
    await summaryPngBlob("b", [], [{ title: "Pequeno", svg: makeSvg(100) }], 1);
    const [, , , w, h] = ctx.drawImage.mock.calls[0];
    expect(w).toBe(100);
    expect(h).toBe(50);
  });

  it("downloadBlob clica num link com o nome do arquivo", () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const seen: string[] = [];
    const orig = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = orig(tag);
      if (tag === "a") seen.push("a");
      return el;
    });
    downloadBlob(new Blob(["x"]), "b-status.png");
    expect(click).toHaveBeenCalled();
    expect(seen).toContain("a");
  });
});
