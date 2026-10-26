import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SvgLegend } from "./SvgLegend";

describe("SvgLegend", () => {
  it("desenha rótulos e cores como elementos do próprio SVG", () => {
    const { container } = render(
      <svg>
        <SvgLegend items={[{ label: "Tool", color: "var(--cobre-text-muted)" }]} />
      </svg>,
    );
    expect(container.querySelector("svg text")?.textContent).toBe("Tool");
    expect(container.querySelector("svg rect")?.getAttribute("fill")).toBe("var(--cobre-text-muted)");
  });
});
