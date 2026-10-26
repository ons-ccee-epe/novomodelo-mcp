import { useParams } from "react-router-dom";

import { useHistory } from "@/services/api/useHistory";
import { useLauncher } from "@/services/api/useLauncher";
import { BatchDashboard } from "./components/BatchDashboard";
import { BatchList } from "./components/BatchList";

const NOOP = () => {};

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
      {selected ? (
        <BatchDashboard
          key={selected.batch_id}
          batch={selected}
          all={batches}
          baselines={baselines}
          launcherOnline={launcher.available}
          onToggleBaseline={toggleBaseline}
        />
      ) : (
        <section aria-label="Dashboard da bateria">Selecione uma bateria</section>
      )}
    </div>
  );
}
