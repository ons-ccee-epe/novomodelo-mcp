import { conjuntoOf } from "./conjunto";
import type { BatchResult } from "./types";

export type Reference = { batch: BatchResult; kind: "baseline" | "anterior" };

export function pickReference(
  batch: BatchResult,
  all: BatchResult[],
  baselines: Record<string, string>,
): Reference | null {
  const conjunto = conjuntoOf(batch);
  const baselineId = baselines[conjunto];
  if (baselineId && baselineId !== batch.batch_id) {
    const baseline = all.find((b) => b.batch_id === baselineId);
    if (baseline) return { batch: baseline, kind: "baseline" };
  }
  const previous = all
    .filter(
      (b) =>
        b.batch_id !== batch.batch_id &&
        conjuntoOf(b) === conjunto &&
        b.timestamp < batch.timestamp,
    )
    .sort((a, b) => (a.timestamp < b.timestamp ? 1 : -1))[0];
  return previous ? { batch: previous, kind: "anterior" } : null;
}

export function comparableIds(a: BatchResult, b: BatchResult): string[] {
  const statusB = new Map(b.test_results.map((r) => [r.test_id, r.status]));
  return a.test_results
    .filter((r) => r.status !== "skip" && statusB.has(r.test_id) && statusB.get(r.test_id) !== "skip")
    .map((r) => r.test_id);
}

export function passRate(batch: BatchResult, ids?: string[]): number | null {
  const wanted = ids ? new Set(ids) : null;
  const rows = wanted
    ? batch.test_results.filter((r) => wanted.has(r.test_id))
    : batch.test_results;
  if (rows.length === 0) return null;
  return (rows.filter((r) => r.status === "pass").length / rows.length) * 100;
}

export function deltaPp(cur: BatchResult, ref: BatchResult): number | null {
  const ids = comparableIds(cur, ref);
  if (ids.length === 0) return null;
  return (passRate(cur, ids) as number) - (passRate(ref, ids) as number);
}

export function changes(
  cur: BatchResult,
  ref: BatchResult,
): { broke: string[]; fixed: string[] } {
  const refStatus = new Map(ref.test_results.map((r) => [r.test_id, r.status]));
  const curStatus = new Map(cur.test_results.map((r) => [r.test_id, r.status]));
  const broke: string[] = [];
  const fixed: string[] = [];
  for (const id of comparableIds(cur, ref)) {
    const wasPass = refStatus.get(id) === "pass";
    const isPass = curStatus.get(id) === "pass";
    if (wasPass && !isPass) broke.push(id);
    else if (!wasPass && isPass) fixed.push(id);
  }
  return { broke, fixed };
}
