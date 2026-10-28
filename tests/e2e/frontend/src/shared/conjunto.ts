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

/** Rótulo curto da tag: cabe no card e a cor diz o grupo. */
export function conjuntoTag(c: string): string {
  if (c === "todos") return "Esteira";
  if (c.startsWith("grupo:")) return c.slice("grupo:".length);
  if (c.startsWith("pergunta:")) return "Avulsa";
  return c;
}

/** Texto da pergunta de uma bateria avulsa; null para esteira e grupo. */
export function conjuntoQuestion(batch: BatchResult): string | null {
  const c = conjuntoOf(batch);
  if (!c.startsWith("pergunta:")) return null;
  const id = c.slice("pergunta:".length);
  return batch.test_results.find((r) => r.test_id === id)?.query ?? null;
}

/** Nome para leitura: a pergunta das avulsas; o rótulo do conjunto nos demais. */
export function conjuntoTitle(batch: BatchResult): string {
  return conjuntoQuestion(batch) ?? conjuntoLabel(conjuntoOf(batch));
}

export function conjuntoColor(c: string): string {
  if (c === "todos") return "var(--nm-set-todos)";
  if (c.startsWith("pergunta:")) return "var(--nm-set-avulsa)";
  let hash = 0;
  for (const ch of c) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return `var(--nm-set-${(hash % PALETTE_SIZE) + 1})`;
}
