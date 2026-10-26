import { useParams } from "react-router-dom";

import { useHistory } from "@/services/api/useHistory";
import { useLauncher } from "@/services/api/useLauncher";
import type { BatchResult } from "@/shared/types";
import { BatchList } from "./components/BatchList";

const NOOP = () => {};

function BatchDashboard({ batch }: { batch: BatchResult | null }) {
  return (
    <section aria-label="Dashboard da bateria">
      {batch ? batch.batch_id : "Selecione uma bateria"}
    </section>
  );
}

export function History() {
  const { batchId } = useParams();
  const { batches, baselines, loading, error, toggleBaseline } = useHistory();
  const launcher = useLauncher(NOOP);

  const selected = batches.find((b) => b.batch_id === (batchId ?? batches[0]?.batch_id)) ?? null;

  return (
    <div className="cobre-history">
      {error && (
        <div className="cobre-banner" data-kind="critical" role="alert">
          {error}
        </div>
      )}
      <aside className="cobre-history-side">
        {!loading && !error && batches.length === 0 ? (
          <p>Nenhuma bateria gravada</p>
        ) : (
          <BatchList
            batches={batches}
            baselines={baselines}
            selectedId={selected?.batch_id ?? null}
            canToggle={launcher.available}
            onToggleBaseline={toggleBaseline}
          />
        )}
      </aside>
      <BatchDashboard batch={selected} />
    </div>
  );
}
