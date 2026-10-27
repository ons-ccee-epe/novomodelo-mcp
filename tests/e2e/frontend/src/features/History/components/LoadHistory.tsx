import { useParams } from "react-router-dom";

import { LoadList } from "@/features/Load/components/LoadList";
import { LoadResult } from "@/features/Load/components/LoadResult";
import { useLoadResults } from "@/services/api/useLoadResults";
import { HistoryKindSwitch } from "./HistoryKindSwitch";

interface Props {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

/** Cargas gravadas no Histórico: a lista à esquerda e o dashboard da selecionada à direita. */
export function LoadHistory({ collapsed, onToggleCollapsed }: Props) {
  const { loadId } = useParams();
  const d = useLoadResults(loadId);

  return (
    <div className="cobre-history" data-collapsed={collapsed}>
      {d.error && (
        <div className="cobre-banner" data-kind="critical" role="alert">
          Erro ao carregar as cargas gravadas: {d.error}
          <div className="cobre-banner-note">
            Verifique se o dev server serve <code>/data/results/load/</code>.
          </div>
        </div>
      )}
      <aside className="cobre-history-side">
        {!collapsed && <HistoryKindSwitch loads />}
        {d.loading && d.runs.length === 0 ? (
          <p className="cobre-no-data">Carregando cargas…</p>
        ) : !d.error && d.runs.length === 0 ? (
          <p className="cobre-no-data">Nenhuma carga gravada</p>
        ) : (
          <LoadList
            runs={d.runs}
            selectedId={d.selectedId}
            collapsed={collapsed}
            onToggleCollapsed={onToggleCollapsed}
            onReload={d.reload}
          />
        )}
      </aside>
      <div className="cobre-history-main cobre-load-main">
        {d.run ? (
          <LoadResult key={d.run.load_id} run={d.run} data={d} />
        ) : d.runs.length > 0 ? (
          <div className="cobre-muted">Carregando a carga selecionada…</div>
        ) : (
          !d.loading && (
            <section className="cobre-history-empty" aria-label="Dashboard da carga">
              Dispare uma carga em Testes de Carga, ou rode{" "}
              <code>python -m tests.e2e.load.run --concurrency 2 --duration 10</code>.
            </section>
          )
        )}
      </div>
    </div>
  );
}
