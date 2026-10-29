import { Link } from "react-router-dom";

import type { ResumoRodada } from "@/data/rodada";
import { historyRodadaPath } from "@/shared/constants/Routes";
import { formatDate } from "../format";

interface Props {
  rodadas: ResumoRodada[];
  selectedId: string | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onReload: () => void;
}

/** Lista lateral das rodadas gravadas. */
export function RodadaList({ rodadas, selectedId, collapsed, onToggleCollapsed, onReload }: Props) {
  const collapseButton = (
    <button
      type="button"
      className="nm-collapse-btn"
      aria-label={collapsed ? "Mostrar a lista de rodadas" : "Recolher a lista de rodadas"}
      aria-expanded={!collapsed}
      onClick={onToggleCollapsed}
    >
      {collapsed ? "›" : "‹"}
    </button>
  );

  if (collapsed) return <div className="nm-batch-list-head">{collapseButton}</div>;

  return (
    <div className="nm-batch-list">
      <div className="nm-batch-list-head">
        <h2>Rodadas</h2>
        <button
          type="button"
          className="nm-collapse-btn"
          aria-label="Atualizar a lista de rodadas"
          title="Atualizar"
          onClick={onReload}
        >
          <span aria-hidden>↻</span>
        </button>
        {collapseButton}
      </div>
      <ul className="nm-batch-items" aria-label="Rodadas gravadas">
        {rodadas.map((r) => (
          <li
            key={r.rodada}
            className="nm-batch-card"
            aria-current={r.rodada === selectedId ? "true" : undefined}
          >
            <Link className="nm-batch-link" to={historyRodadaPath(r.rodada)}>
              {r.rodada}
            </Link>
            <span className="nm-batch-tags">
              {r.em_andamento && (
                <span className="nm-pill" data-tone="running">
                  em andamento
                </span>
              )}
              {r.erro && (
                <span className="nm-pill" data-tone="fail">
                  ilegível
                </span>
              )}
            </span>
            <span className="nm-batch-counts">
              {r.criado_em ? formatDate(r.criado_em) : "—"}
              {(r.configs ?? []).length > 0 ? ` · ${(r.configs ?? []).join(", ")}` : ""}
              {(r.agentes ?? []).length > 0 ? ` · ${(r.agentes ?? []).join(", ")}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
