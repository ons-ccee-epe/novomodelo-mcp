import { useCallback, useEffect, useState } from "react";
import type { BatchResult } from "@/shared/types";
import { conjuntoOf } from "@/shared/conjunto";
import { fetchBaselineFile, fetchBatch, fetchIndex } from "@/services/resultsApi";
import { clearBaseline, setBaseline } from "@/services/launcherApi";

export interface HistoryData {
  batches: BatchResult[];
  baselines: Record<string, string>;
  loading: boolean;
  error: string | null;
  reload: () => void;
  toggleBaseline: (batch: BatchResult) => Promise<void>;
}

function resolveBaselines(
  file: Awaited<ReturnType<typeof fetchBaselineFile>>,
  batches: BatchResult[],
): Record<string, string> {
  const known = new Set(batches.map((b) => b.batch_id));
  const merged = { ...file.baselines };
  const legacy = batches.find((b) => b.batch_id === file.legacyId);
  if (legacy) merged[conjuntoOf(legacy)] ??= legacy.batch_id;
  return Object.fromEntries(Object.entries(merged).filter(([, id]) => known.has(id)));
}

/** Todas as baterias (mais recente primeiro) e as baselines por conjunto. */
export function useHistory(): HistoryData {
  const [batches, setBatches] = useState<BatchResult[]>([]);
  const [baselines, setBaselines] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    (async () => {
      const [index, file] = await Promise.all([fetchIndex(), fetchBaselineFile()]);
      const all = await Promise.all(index.batches.map((e) => fetchBatch(e.batch_id)));
      all.sort((a, b) => (b.timestamp ?? "").localeCompare(a.timestamp ?? ""));
      if (!alive) return;
      setBatches(all);
      setBaselines(resolveBaselines(file, all));
    })()
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [tick]);

  const toggleBaseline = useCallback(
    async (batch: BatchResult) => {
      const conjunto = conjuntoOf(batch);
      if (baselines[conjunto] === batch.batch_id) await clearBaseline(conjunto);
      else await setBaseline(conjunto, batch.batch_id);
      const file = await fetchBaselineFile();
      setBaselines(resolveBaselines(file, batches));
    },
    [baselines, batches],
  );

  return { batches, baselines, loading, error, reload, toggleBaseline };
}
