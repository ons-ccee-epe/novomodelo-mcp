import { useCallback, useEffect, useRef, useState } from "react";

import { fetchLoadIndex, fetchLoadRun } from "@/services/loadApi";
import type { LoadIndexEntry, LoadRun } from "@/shared/types";

export interface LoadResultsData {
  loading: boolean;
  error: string | null;
  /** Cargas gravadas, mais recente primeiro. */
  runs: LoadIndexEntry[];
  selectedId: string | null;
  /** Carga de comparação efetiva (por padrão, a imediatamente anterior à selecionada). */
  compareId: string | null;
  run: LoadRun | null;
  compareRun: LoadRun | null;
  selectRun: (id: string) => void;
  /** ``null`` = sem comparação; ``undefined`` = voltar ao padrão (a anterior). */
  selectCompare: (id: string | null | undefined) => void;
  reload: () => void;
  /** Seleciona uma carga recém-gravada assim que o index a listar. */
  showNewest: () => void;
}

function previousOf(runs: LoadIndexEntry[], id: string | null): string | null {
  if (!id) return null;
  const index = runs.findIndex((r) => r.load_id === id);
  return index >= 0 ? (runs[index + 1]?.load_id ?? null) : null;
}

/**
 * Carrega as cargas gravadas (somente leitura, de /data/results/load): o index, a carga
 * selecionada (default = mais recente) e a de comparação (default = a anterior).
 */
export function useLoadResults(): LoadResultsData {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<LoadIndexEntry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareChoice, setCompareChoice] = useState<string | null | undefined>(undefined);
  const [run, setRun] = useState<LoadRun | null>(null);
  const [compareRun, setCompareRun] = useState<LoadRun | null>(null);
  const [tick, setTick] = useState(0);
  const followNewest = useRef(false);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const showNewest = useCallback(() => {
    followNewest.current = true;
    setTick((t) => t + 1);
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fetchLoadIndex()
      .then((entries) => {
        if (!alive) return;
        setRuns(entries);
        setSelectedId((current) => {
          const keep = !followNewest.current && current;
          if (keep && entries.some((r) => r.load_id === current)) return current;
          return entries[0]?.load_id ?? null;
        });
        followNewest.current = false;
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

  const compareId =
    compareChoice === undefined ? previousOf(runs, selectedId) : compareChoice;
  const effectiveCompareId = compareId && compareId !== selectedId ? compareId : null;

  useEffect(() => {
    if (!selectedId) {
      setRun(null);
      return;
    }
    let alive = true;
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

  const selectRun = useCallback((id: string) => {
    setSelectedId(id);
    setCompareChoice(undefined);
  }, []);

  return {
    loading,
    error,
    runs,
    selectedId,
    compareId: effectiveCompareId,
    run,
    compareRun,
    selectRun,
    selectCompare: setCompareChoice,
    reload,
    showNewest,
  };
}
