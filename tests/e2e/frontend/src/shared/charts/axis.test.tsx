import { render, screen } from "@testing-library/react";
import { DefaultTooltipContent } from "recharts";
import { describe, expect, it } from "vitest";

import { TOOLTIP, tooltipNumber } from "./axis";

describe("tooltip dos gráficos", () => {
  it("formata números com uma casa no padrão brasileiro", () => {
    expect(tooltipNumber(98276.28089999962)).toBe("98.276,3");
    expect(tooltipNumber(0)).toBe("0");
    expect(tooltipNumber("docs")).toBe("docs");
  });

  it("usa as cores do tema no fundo, no título e nos itens", () => {
    const { contentStyle, labelStyle, itemStyle, formatter } = TOOLTIP;
    render(
      <DefaultTooltipContent
        label="results-policy-get"
        payload={[{ name: "Total", value: 98276.28089999962, color: "red", dataKey: "total" }]}
        contentStyle={contentStyle}
        labelStyle={labelStyle}
        itemStyle={itemStyle}
        formatter={formatter}
      />,
    );
    expect(screen.getByText("98.276,3")).toBeInTheDocument();
    expect(screen.getByText("results-policy-get")).toHaveStyle({ color: "var(--nm-text)" });
    expect(screen.getByText("Total").closest("li")).toHaveStyle({ color: "var(--nm-text)" });
  });
});
