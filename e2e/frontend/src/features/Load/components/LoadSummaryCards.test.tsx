import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeLoadRun } from "../fixtures";
import { LoadSummaryCards } from "./LoadSummaryCards";

describe("LoadSummaryCards", () => {
  it("mostra quantas sessões simultâneas a carga usou", () => {
    const run = makeLoadRun();
    render(
      <LoadSummaryCards
        run={{
          ...run,
          config: { ...run.config, concurrency: 4 },
          startup: { ...run.startup, clients: 4, started: 4 },
        }}
      />,
    );
    const card = screen.getByText("Sessões simultâneas").closest(".nm-card");
    expect(card).toHaveTextContent("4");
  });

  it("avisa quando nem todas as sessões subiram", () => {
    const run = makeLoadRun();
    render(
      <LoadSummaryCards
        run={{
          ...run,
          config: { ...run.config, concurrency: 4 },
          startup: { ...run.startup, clients: 4, started: 3 },
        }}
      />,
    );
    expect(screen.getByText("Sessões simultâneas (3 subiram)")).toBeInTheDocument();
  });
});
