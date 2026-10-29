import { useState } from "react";
import { useMatch, useParams } from "react-router-dom";

import { useRodada, useRodadas } from "@/services/api/useRodadas";
import { ROUTES } from "@/shared/constants/Routes";
import { HistoryKindSwitch } from "./components/HistoryKindSwitch";
import { LoadHistory } from "./components/LoadHistory";
import { RodadaDashboard } from "./components/RodadaDashboard";
import { RodadaList } from "./components/RodadaList";

interface CollapseProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

function RodadaHistory({ collapsed, onToggleCollapsed }: CollapseProps) {
  const { rodadaId } = useParams();
  const { rodadas, loading, error, reload } = useRodadas();
  const selectedId = rodadaId ?? rodadas[0]?.rodada ?? null;
  const selecionada = useRodada(selectedId);

  return (
    <div className="nm-history" data-collapsed={collapsed}>
      {error && (
        <div className="nm-banner" data-kind="critical" role="alert">
          {error}
        </div>
      )}
      <aside className="nm-history-side">
        {!collapsed && <HistoryKindSwitch loads={false} />}
        {loading && rodadas.length === 0 ? (
          <p className="nm-no-data">Carregando rodadas…</p>
        ) : !error && rodadas.length === 0 ? (
          <p className="nm-no-data">Nenhuma rodada gravada</p>
        ) : (
          <RodadaList
            rodadas={rodadas}
            selectedId={selectedId}
            collapsed={collapsed}
            onToggleCollapsed={onToggleCollapsed}
            onReload={reload}
          />
        )}
      </aside>
      <div className="nm-history-main">
        {selecionada.error && (
          <div className="nm-banner" data-kind="critical" role="alert">
            {selecionada.error}
          </div>
        )}
        {selecionada.rodada ? (
          <RodadaDashboard key={selecionada.rodada.rodada} rodada={selecionada.rodada} todas={rodadas} />
        ) : selecionada.loading ? (
          <div className="nm-muted">Carregando a rodada selecionada…</div>
        ) : (
          !selecionada.error && (
            <section className="nm-history-empty" aria-label="Dashboard da rodada">
              Selecione uma rodada
            </section>
          )
        )}
      </div>
    </div>
  );
}

/** Histórico: rodadas da bateria ou cargas gravadas, cada uma com lista e dashboard. */
export function History() {
  const showLoads = useMatch(`${ROUTES.historyLoad.path}/*`) !== null;
  const [collapsed, setCollapsed] = useState(false);
  const toggle = () => setCollapsed((v) => !v);

  return showLoads ? (
    <LoadHistory collapsed={collapsed} onToggleCollapsed={toggle} />
  ) : (
    <RodadaHistory collapsed={collapsed} onToggleCollapsed={toggle} />
  );
}
