import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChartCard } from "./ChartCard";

describe("ChartCard", () => {
  it("mostra o título e o botão de download", () => {
    render(
      <ChartCard title="Status" fileName="b-status.png">
        <svg />
      </ChartCard>,
    );
    expect(screen.getByText("Status")).toBeTruthy();
    expect(screen.getByRole("button", { name: "⤓ PNG" })).toBeTruthy();
  });
});
