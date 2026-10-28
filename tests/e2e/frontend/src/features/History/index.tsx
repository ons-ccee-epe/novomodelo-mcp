import { useState } from "react";
import { useMatch, useParams } from "react-router-dom";

import { useHistory } from "@/services/api/useHistory";
import { useLauncher } from "@/services/api/useLauncher";
import { ROUTES } from "@/shared/constants/Routes";
import { BatchDashboard } from "./components/BatchDashboard";
import { BatchList } from "./components/BatchList";
import { HistoryKindSwitch } from "./components/HistoryKindSwitch";
import { LoadHistory } from "./components/LoadHistory";

const NOOP = () => {};

interface CollapseProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

function BatchHistory({ collapsed, onToggleCollapsed }: CollapseProps) {
  const { batchId } = useParams();
  const { batches, baselines, loading, error, unreadable, toggleBaseline } =
    useHistory();
  const launcher = useLauncher(NOOP);

  const selected =
    batches.find((b) => b.batch_id === (batchId ?? batches[0]?.batch_id)) ??
    null;

  return (
    <div className="nm-history" data-collapsed={collapsed}>
      {error && (
        <div className="nm-banner" data-kind="critical" role="alert">
          {error}
        </div>
      )}
      <aside className="nm-history-side">
        {!collapsed && <HistoryKindSwitch loads={false} />}
        {loading && batches.length === 0 ? (
          <p className="nm-no-data">Carregando baterias…</p>
        ) : !error && batches.length === 0 ? (
          <p className="nm-no-data">Nenhuma bateria gravada</p>
        ) : (
          <BatchList
            batches={batches}
            baselines={baselines}
            selectedId={selected?.batch_id ?? null}
            collapsed={collapsed}
            onToggleCollapsed={onToggleCollapsed}
          />
        )}
        {unreadable > 0 && !collapsed && (
          <p className="nm-muted">
            {unreadable}{" "}
            {unreadable === 1
              ? "bateria não pôde ser lida"
              : "baterias não puderam ser lidas"}
          </p>
        )}
      </aside>
      <div className="nm-history-main">
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
          <section
            className="nm-history-empty"
            aria-label="Dashboard da bateria"
          >
            Selecione uma bateria
          </section>
        )}
      </div>
    </div>
  );
}

/** Histórico: baterias funcionais ou cargas gravadas, cada uma com lista e dashboard. */
export function History() {
  const showLoads = useMatch(`${ROUTES.historyLoad.path}/*`) !== null;
  const [collapsed, setCollapsed] = useState(false);
  const toggle = () => setCollapsed((v) => !v);

  return showLoads ? (
    <LoadHistory collapsed={collapsed} onToggleCollapsed={toggle} />
  ) : (
    <BatchHistory collapsed={collapsed} onToggleCollapsed={toggle} />
  );
}
