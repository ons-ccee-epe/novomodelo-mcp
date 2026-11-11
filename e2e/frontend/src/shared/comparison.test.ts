import { describe, expect, it } from "vitest";
import { changes, comparableIds, deltaPp, passRate, pickReference } from "./comparison";
import { makeBatch } from "./fixtures.testutil";

const docs = (id: string, ts: string, statuses: Array<"pass" | "fail">) =>
  makeBatch(
    id,
    statuses.map((s, i) => [`q${i + 1}`, s, "docs_list"]),
    { timestamp: ts, conjunto: "grupo:docs" },
  );

describe("pickReference", () => {
  const cur = docs("cur", "2026-03-01T00:00:00", ["pass", "pass"]);
  const old = docs("old", "2026-01-01T00:00:00", ["pass", "fail"]);
  const mid = docs("mid", "2026-02-01T00:00:00", ["pass", "fail"]);
  const other = makeBatch("other", [["q1", "pass", "deck_list"]], {
    timestamp: "2026-02-15T00:00:00",
    conjunto: "grupo:deck",
  });

  it("prefere a baseline do conjunto", () => {
    const ref = pickReference(cur, [cur, old, mid], { "grupo:docs": "old" });
    expect(ref).toEqual({ batch: old, kind: "baseline" });
  });

  it("cai na anterior mais recente do mesmo conjunto", () => {
    const ref = pickReference(cur, [cur, old, mid, other], {});
    expect(ref).toEqual({ batch: mid, kind: "anterior" });
  });

  it("ignora baseline ausente de all", () => {
    const ref = pickReference(cur, [cur, old], { "grupo:docs": "sumiu" });
    expect(ref).toEqual({ batch: old, kind: "anterior" });
  });

  it("não usa a própria bateria como baseline", () => {
    const ref = pickReference(cur, [cur, old], { "grupo:docs": "cur" });
    expect(ref).toEqual({ batch: old, kind: "anterior" });
  });

  it("ignora baterias posteriores e de outro conjunto", () => {
    const later = docs("later", "2026-04-01T00:00:00", ["pass"]);
    expect(pickReference(cur, [cur, later, other], {})).toBeNull();
  });

  it("devolve null sem candidatas", () => {
    expect(pickReference(cur, [cur], {})).toBeNull();
  });
});

describe("comparableIds", () => {
  it("só ids nas duas e não skip em nenhuma", () => {
    const a = makeBatch("a", [
      ["q1", "pass", "docs_list"],
      ["q2", "skip", "docs_list"],
      ["q3", "pass", "docs_list"],
      ["q4", "pass", "docs_list"],
    ]);
    const b = makeBatch("b", [
      ["q1", "fail", "docs_list"],
      ["q2", "pass", "docs_list"],
      ["q3", "skip", "docs_list"],
    ]);
    expect(comparableIds(a, b)).toEqual(["q1"]);
  });
});

describe("passRate", () => {
  it("é percentual e null sem ids", () => {
    const b = docs("b", "t", ["pass", "fail", "pass", "pass"]);
    expect(passRate(b)).toBe(75);
    expect(passRate(b, ["q1", "q2"])).toBe(50);
    expect(passRate(b, [])).toBeNull();
  });
});

describe("deltaPp", () => {
  it("compara só as perguntas em comum", () => {
    const cur = makeBatch("c", [
      ["q1", "pass", "docs_list"],
      ["q2", "pass", "docs_list"],
      ["q3", "pass", "docs_list"],
      ["q4", "fail", "docs_list"],
      ["novo", "pass", "docs_list"],
    ]);
    const ref = makeBatch("r", [
      ["q1", "pass", "docs_list"],
      ["q2", "pass", "docs_list"],
      ["q3", "fail", "docs_list"],
      ["q4", "fail", "docs_list"],
    ]);
    expect(deltaPp(cur, ref)).toBe(25);
  });

  it("null sem ids em comum ou com tudo skip", () => {
    const a = makeBatch("a", [["q1", "pass", "docs_list"]]);
    const b = makeBatch("b", [["q2", "pass", "docs_list"]]);
    expect(deltaPp(a, b)).toBeNull();
    const s1 = makeBatch("s1", [["q1", "skip", "docs_list"]]);
    const s2 = makeBatch("s2", [["q1", "skip", "docs_list"]]);
    expect(deltaPp(s1, s2)).toBeNull();
  });
});

describe("changes", () => {
  it("lista quebradas e consertadas", () => {
    const ref = makeBatch("r", [
      ["q1", "pass", "docs_list"],
      ["q2", "fail", "docs_list"],
      ["q3", "pass", "docs_list"],
      ["q4", "pass", "docs_list"],
    ]);
    const cur = makeBatch("c", [
      ["q1", "fail", "docs_list"],
      ["q2", "pass", "docs_list"],
      ["q3", "pass", "docs_list"],
      ["q4", "skip", "docs_list"],
    ]);
    expect(changes(cur, ref)).toEqual({ broke: ["q1"], fixed: ["q2"] });
  });
});
