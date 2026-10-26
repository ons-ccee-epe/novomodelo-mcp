import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { setBaseline, type RunState } from "@/services/launcherApi";
import { fetchBatch } from "@/services/resultsApi";
import { historyBatchPath } from "@/shared/constants/Routes";
import { conjuntoOf } from "@/shared/conjunto";

/** Ações ao fim de uma rodada concluída que gravou bateria. */
export function RunFinished({ run }: { run: RunState }) {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const batchId = run.batch_id;
  if (run.status !== "done" || !batchId) return null;

  async function defineBaseline(id: string) {
    setSaving(true);
    setError(null);
    try {
      const batch = await fetchBatch(id);
      await setBaseline(conjuntoOf(batch), id);
      setDone(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="cobre-run-finished">
      <button
        type="button"
        className="cobre-btn cobre-btn-primary"
        onClick={() => navigate(historyBatchPath(batchId))}
      >
        Resumo de resultados
      </button>
      {done ? (
        <span className="cobre-muted">Baseline definida</span>
      ) : (
        <button
          type="button"
          className="cobre-btn"
          disabled={saving}
          onClick={() => void defineBaseline(batchId)}
        >
          Definir como baseline
        </button>
      )}
      {error && (
        <span role="alert" className="cobre-run-finished-error">
          {error}
        </span>
      )}
    </div>
  );
}
