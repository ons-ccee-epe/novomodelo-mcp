import { useNavigate } from "react-router-dom";

import type { RunState } from "@/services/launcherApi";
import { historyBatchPath } from "@/shared/constants/Routes";

/** Ao fim de uma rodada que gravou bateria, leva ao dashboard dela no Histórico. */
export function RunFinished({ run }: { run: RunState }) {
  const navigate = useNavigate();
  const batchId = run.batch_id;
  if (run.status !== "done" || !batchId) return null;

  return (
    <button
      type="button"
      className="nm-btn nm-btn-primary nm-btn-sm"
      onClick={() => navigate(historyBatchPath(batchId))}
    >
      Ver resultados no Histórico
    </button>
  );
}
