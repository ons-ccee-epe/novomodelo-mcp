import { useCallback, useEffect, useState } from "react";

import { fetchLoadIndex, fetchLoadRun } from "@/services/loadApi";
import { indexEntryMode, type LoadIndexEntry, type SavedLoadRun } from "@/shared/types";

export interface LoadResultsData {
  loading: boolean;
  error: string | null;
  /** Cargas gravadas, mais recente primeiro. */
  runs: LoadIndexEntry[];
  selectedId: string | null;
  /** Carga de comparação efetiva (por padrão, a imediatamente anterior à selecionada). */
  compareId: string | null;
  run: SavedLoadRun | null;
  compareRun: SavedLoadRun | null;
  /** ``null`` = sem comparação; ``undefined`` = voltar ao padrão (a anterior). */
  selectCompare: (id: string | null | undefined) => void;
  reload: () => void;
}

/** A carga imediatamente anterior do MESMO modo: tools e agente não se comparam. */
function previousOf(runs: LoadIndexEntry[], id: string | null): string | null {
  if (!id) return null;
  const index = runs.findIndex((r) => r.load_id === id);
  if (index < 0) return null;
  const mode = indexEntryMode(runs[index]);
  return runs.slice(index + 1).find((r) => indexEntryMode(r) === mode)?.load_id ?? null;
}

function sameMode(runs: LoadIndexEntry[], a: string | null, b: string): boolean {
  const first = runs.find((r) => r.load_id === a);
  const second = runs.find((r) => r.load_id === b);
  return Boolean(first && second && indexEntryMode(first) === indexEntryMode(second));
}

/**
 * Carrega as cargas gravadas (somente leitura, de /data/results/load): o index, a carga
 * pedida na URL (sem ela, a mais recente) e a de comparação (por padrão, a anterior).
 */
export function useLoadResults(requestedId?: string): LoadResultsData {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<LoadIndexEntry[]>([]);
  const [compare, setCompare] = useState<{ for: string | null; choice: string | null | undefined }>(
    { for: null, choice: undefined },
  );
  const [run, setRun] = useState<SavedLoadRun | null>(null);
  const [compareRun, setCompareRun] = useState<SavedLoadRun | null>(null);
  const [tick, setTick] = useState(0);

  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fetchLoadIndex()
      .then((entries) => alive && setRuns(entries))
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

  const selectedId = requestedId ?? runs[0]?.load_id ?? null;
  const compareChoice = compare.for === selectedId ? compare.choice : undefined;
  const compareId = compareChoice === undefined ? previousOf(runs, selectedId) : compareChoice;
  const effectiveCompareId =
    compareId && compareId !== selectedId && sameMode(runs, selectedId, compareId)
      ? compareId
      : null;

  useEffect(() => {
    if (!selectedId) {
      setRun(null);
      return;
    }
    let alive = true;
    setRun(null);
    fetchLoadRun(selectedId)
      .then((r) => alive && setRun(r))
      .catch((e: unknown) => {
        if (alive) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!effectiveCompareId) {
      setCompareRun(null);
      return;
    }
    let alive = true;
    fetchLoadRun(effectiveCompareId)
      .then((r) => alive && setCompareRun(r))
      .catch(() => alive && setCompareRun(null));
    return () => {
      alive = false;
    };
  }, [effectiveCompareId]);

  const selectCompare = useCallback(
    (choice: string | null | undefined) => setCompare({ for: selectedId, choice }),
    [selectedId],
  );

  return {
    loading,
    error,
    runs,
    selectedId,
    compareId: effectiveCompareId,
    run,
    compareRun,
    selectCompare,
    reload,
  };
}
