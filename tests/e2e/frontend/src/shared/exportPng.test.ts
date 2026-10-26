import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { downloadBlob, summaryPngBlob, svgToPngBlob } from "./exportPng";

const drawn: string[] = [];

function mockEnv() {
  drawn.length = 0;
  vi.stubGlobal(
    "getComputedStyle",
    () => ({ getPropertyValue: (n: string) => (n === "--cobre-pass" ? "#22c55e" : "#ffffff") }),
  );
  const ctx = {
    scale: vi.fn(),
    fillRect: vi.fn(),
    drawImage: vi.fn(),
    fillText: vi.fn((t: string) => drawn.push(t)),
    set fillStyle(_v: string) {},
    set font(_v: string) {},
    set textBaseline(_v: string) {},
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

function makeSvg(): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "100");
  svg.setAttribute("height", "50");
  const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  rect.setAttribute("fill", "var(--cobre-pass)");
  svg.appendChild(rect);
  return svg;
}

describe("exportPng", () => {
  beforeEach(() => {
    vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("svgToPngBlob troca var(--cobre-*) pela cor computada", async () => {
    const { sources } = mockEnv();
    const blob = await svgToPngBlob(makeSvg());
    expect(blob.type).toBe("image/png");
    expect(sources[0]).toContain("#22c55e");
    expect(sources[0]).not.toContain("var(--cobre-pass)");
  });

  it("summaryPngBlob escreve título e cards no canvas", async () => {
    mockEnv();
    const blob = await summaryPngBlob("bateria x", [{ label: "Total", value: "4" }], [makeSvg()]);
    expect(blob.type).toBe("image/png");
    expect(drawn).toContain("bateria x");
    expect(drawn).toContain("Total");
    expect(drawn).toContain("4");
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
