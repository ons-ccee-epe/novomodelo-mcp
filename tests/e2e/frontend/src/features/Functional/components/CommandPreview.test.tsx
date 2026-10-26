import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CommandPreview as Preview } from "@/services/launcherApi";
import { CommandPreview } from "./CommandPreview";

const PREVIEW: Preview = {
  conjunto: "todos",
  total: 3,
  terminal: "python -m tests.e2e.run --provider claude",
  terminal_note: null,
  agent: "claude -p 'pergunta'",
};

function stubFetch(body: Preview | null) {
  const mock = vi.fn(async () =>
    body
      ? ({ ok: true, status: 200, json: async () => body } as Response)
      : ({ ok: false, status: 500, json: async () => ({}) } as Response),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CommandPreview", () => {
  it("mostra o comando do terminal e o do agente", async () => {
    stubFetch(PREVIEW);
    render(<CommandPreview provider="claude" scope={{}} />);

    expect(await screen.findByText("Bateria pelo terminal")).toBeInTheDocument();
    expect(screen.getByText(PREVIEW.terminal!)).toBeInTheDocument();
    expect(screen.getByText("Comando do agente por pergunta")).toBeInTheDocument();
    expect(screen.getByText(PREVIEW.agent)).toBeInTheDocument();
  });

  it("mostra a nota quando não há comando de terminal", async () => {
    stubFetch({ ...PREVIEW, terminal: null, terminal_note: "Sem equivalente no terminal." });
    render(<CommandPreview provider="claude" scope={{ caseId: "q1" }} />);

    expect(await screen.findByText("Sem equivalente no terminal.")).toBeInTheDocument();
    expect(screen.queryByText(PREVIEW.terminal!)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Copiar" })).toHaveLength(1);
  });

  it("Copiar envia o texto exato ao clipboard", async () => {
    stubFetch(PREVIEW);
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    render(<CommandPreview provider="claude" scope={{}} />);

    await screen.findByText("Bateria pelo terminal");
    const [terminalBtn, agentBtn] = screen.getAllByRole("button", { name: "Copiar" });
    fireEvent.click(terminalBtn);
    expect(writeText).toHaveBeenLastCalledWith(PREVIEW.terminal);
    fireEvent.click(agentBtn);
    expect(writeText).toHaveBeenLastCalledWith(PREVIEW.agent);
  });

  it("não renderiza nada quando a busca falha", async () => {
    const mock = stubFetch(null);
    const { container } = render(<CommandPreview provider="claude" scope={{}} />);
    await vi.waitFor(() => expect(mock).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(container).toBeEmptyDOMElement();
  });
});
