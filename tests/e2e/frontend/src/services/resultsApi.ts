/**
 * Camada de dados do dashboard E2E.
 *
 * Le os resultados dos testes diretamente dos JSON gravados pelo ResultStore,
 * servidos sob /data/ (plugin de dev do Vite ou pasta estatica no build).
 * Sem backend: apenas fetch de arquivos.
 */
import type {
  BatchIndex,
  BatchResult,
  MetricsHistoryRecord,
} from "@/shared/types";

const BASE = "data";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Falha ao carregar ${path}: HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

/** index.json com todas as baterias, ordenado por timestamp desc. */
export async function fetchIndex(): Promise<BatchIndex> {
  const index = await getJson<BatchIndex>("results/index.json");
  const batches = [...(index.batches ?? [])].sort((a, b) =>
    (b.timestamp ?? "").localeCompare(a.timestamp ?? ""),
  );
  return { batches };
}

/** Uma bateria completa pelo batch_id. */
export async function fetchBatch(batchId: string): Promise<BatchResult> {
  return getJson<BatchResult>(`results/${batchId}.json`);
}

/** batch_id da baseline, se definida (baseline.json). */
export async function fetchBaselineId(): Promise<string | null> {
  try {
    const data = await getJson<{ batch_id?: string }>("results/baseline.json");
    return data.batch_id ?? null;
  } catch {
    return null;
  }
}

/**
 * Historico de metricas (metrics/history.jsonl), mais antigo primeiro,
 * para os graficos de tendencia. O arquivo e JSONL: uma linha por record.
 */
export async function fetchMetricsHistory(): Promise<MetricsHistoryRecord[]> {
  const res = await fetch(`${BASE}/metrics/history.jsonl`, { cache: "no-store" });
  if (!res.ok) return [];
  const text = await res.text();
  const records: MetricsHistoryRecord[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      records.push(JSON.parse(trimmed) as MetricsHistoryRecord);
    } catch {
      // Ignora linhas malformadas, como o ResultStore faz.
    }
  }
  records.sort((a, b) => (a.timestamp ?? "").localeCompare(b.timestamp ?? ""));
  return records;
}
