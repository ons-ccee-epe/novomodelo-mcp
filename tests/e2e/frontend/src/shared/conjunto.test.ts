import { describe, expect, it } from "vitest";
import { conjuntoColor, conjuntoLabel, conjuntoOf } from "./conjunto";
import { makeBatch } from "./fixtures.testutil";

describe("conjuntoOf", () => {
  it("usa o campo quando existe", () => {
    const b = makeBatch("a", [["q1", "pass", "docs_list"]], { conjunto: "grupo:deck" });
    expect(conjuntoOf(b)).toBe("grupo:deck");
  });

  it("infere pergunta com um único resultado", () => {
    expect(conjuntoOf(makeBatch("a", [["q1", "pass", "docs_list"]]))).toBe("pergunta:q1");
  });

  it("infere grupo quando todos os resultados são do mesmo grupo", () => {
    const b = makeBatch("a", [
      ["q1", "pass", "docs_list"],
      ["q2", "fail", "docs_read"],
    ]);
    expect(conjuntoOf(b)).toBe("grupo:docs");
  });

  it("infere todos quando os grupos divergem", () => {
    const b = makeBatch("a", [
      ["q1", "pass", "docs_list"],
      ["q2", "pass", "deck_list"],
    ]);
    expect(conjuntoOf(b)).toBe("todos");
  });

  it("usa a primeira de expected_tools e other quando falta a tool", () => {
    const b = makeBatch("a", [
      ["q1", "pass", null],
      ["q2", "pass", null],
    ]);
    b.test_results[0].expected_tools = ["docs_list", "deck_list"];
    expect(conjuntoOf(b)).toBe("todos");
    b.test_results[0].expected_tools = null;
    expect(conjuntoOf(b)).toBe("grupo:other");
  });
});

describe("conjuntoLabel", () => {
  it("rotula cada forma", () => {
    expect(conjuntoLabel("todos")).toBe("Esteira completa");
    expect(conjuntoLabel("grupo:bridge+deck")).toBe("Grupo bridge+deck");
    expect(conjuntoLabel("pergunta:q1")).toBe("Pergunta q1");
  });
});

describe("conjuntoColor", () => {
  it("todos usa o token próprio", () => {
    expect(conjuntoColor("todos")).toBe("var(--cobre-set-todos)");
  });

  it("é estável e fica entre 1 e 8", () => {
    const c = conjuntoColor("grupo:docs");
    expect(conjuntoColor("grupo:docs")).toBe(c);
    expect(c).toMatch(/^var\(--cobre-set-[1-8]\)$/);
  });
});
