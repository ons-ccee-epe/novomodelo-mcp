import { groupForCase } from "./toolGroups";
import type { BatchResult } from "./types";

const PALETTE_SIZE = 8;

export function conjuntoOf(batch: BatchResult): string {
  if (batch.conjunto) return batch.conjunto;
  const results = batch.test_results;
  if (results.length === 1) return `pergunta:${results[0].test_id}`;
  const groups = new Set(results.map(groupForCase));
  if (results.length > 0 && groups.size === 1) return `grupo:${[...groups][0]}`;
  return "todos";
}

export function conjuntoLabel(c: string): string {
  if (c === "todos") return "Esteira completa";
  if (c.startsWith("grupo:")) return `Grupo ${c.slice("grupo:".length)}`;
  if (c.startsWith("pergunta:")) return `Pergunta ${c.slice("pergunta:".length)}`;
  return c;
}

export function conjuntoColor(c: string): string {
  if (c === "todos") return "var(--cobre-set-todos)";
  let hash = 0;
  for (const ch of c) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `var(--cobre-set-${(hash % PALETTE_SIZE) + 1})`;
}
