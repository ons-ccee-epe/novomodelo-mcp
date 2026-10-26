import { useCallback, useEffect, useState } from "react";
import type {
  BatchIndexEntry,
  BatchResult,
  MetricsHistoryRecord,
} from "@/shared/types";
import {
  fetchBaselineFile,
  fetchBatch,
  fetchIndex,
  fetchMetricsHistory,
} from "@/services/resultsApi";

export interface ResultsData {
  loading: boolean;
  error: string | null;
  batches: BatchIndexEntry[];
  selectedId: string | null;
  compareId: string | null;
  baselineId: string | null;
  batch: BatchResult | null;
  compareBatch: BatchResult | null;
  history: MetricsHistoryRecord[];
  selectBatch: (id: string) => void;
  selectCompare: (id: string | null) => void;
  reload: () => void;
}

/**
 * Orquestra o carregamento dos resultados: o index de baterias, a bateria
 * selecionada (default = mais recente), a bateria de comparacao opcional,
 * a baseline e o historico de metricas. Recarrega sob demanda (botao/poll).
 */
export function useResults(): ResultsData {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [batches, setBatches] = useState<BatchIndexEntry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [baselineId, setBaselineId] = useState<string | null>(null);
  const [batch, setBatch] = useState<BatchResult | null>(null);
  const [compareBatch, setCompareBatch] = useState<BatchResult | null>(null);
  const [history, setHistory] = useState<MetricsHistoryRecord[]>([]);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  // Carrega o indice + baseline + historico (e escolhe a bateria default).
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);

    Promise.all([fetchIndex(), fetchBaselineFile(), fetchMetricsHistory()])
      .then(([index, baselineFile, hist]) => {
        if (!alive) return;
        setBatches(index.batches);
        setBaselineId(
          baselineFile.legacyId ?? baselineFile.baselines["todos"] ?? null,
        );
        setHistory(hist);
        setSelectedId((cur) => {
          if (cur && index.batches.some((b) => b.batch_id === cur)) return cur;
          return index.batches[0]?.batch_id ?? null;
        });
      })
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

  // Carrega a bateria selecionada.
  useEffect(() => {
    if (!selectedId) {
      setBatch(null);
      return;
    }
    let alive = true;
    fetchBatch(selectedId)
      .then((b) => alive && setBatch(b))
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [selectedId, tick]);

  // Carrega a bateria de comparacao (opcional).
  useEffect(() => {
    if (!compareId) {
      setCompareBatch(null);
      return;
    }
    let alive = true;
    fetchBatch(compareId)
      .then((b) => alive && setCompareBatch(b))
      .catch(() => alive && setCompareBatch(null));
    return () => {
      alive = false;
    };
  }, [compareId, tick]);

  const selectBatch = useCallback(
    (id: string) => {
      setSelectedId(id);
      if (id === compareId) setCompareId(null);
    },
    [compareId],
  );

  const selectCompare = useCallback((id: string | null) => {
    setCompareId(id || null);
  }, []);

  return {
    loading,
    error,
    batches,
    selectedId,
    compareId,
    baselineId,
    batch,
    compareBatch,
    history,
    selectBatch,
    selectCompare,
    reload,
  };
}
