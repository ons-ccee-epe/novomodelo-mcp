import type { BatchResult } from "@/shared/types";

interface Props {
  batch: BatchResult;
  selectedGroup: string | null;
  onSelectGroup: (group: string | null) => void;
}

/** Metricas por grupo de tools (bridge, deck, docs, ...). Clique filtra a tabela. */
export function MetricsByGroup({ batch, selectedGroup, onSelectGroup }: Props) {
  const groups = Object.entries(batch.metrics_by_group ?? {}).sort(([a], [b]) =>
    a.localeCompare(b),
  );
  const n = (v: number | undefined) => (typeof v === "number" ? v : 0);

  if (groups.length === 0) {
    return (
      <section className="cobre-section">
        <h2 className="cobre-section-title">Métricas por Grupo</h2>
        <div className="cobre-no-data">Nenhuma métrica por grupo disponível</div>
      </section>
    );
  }

  return (
    <section className="cobre-section">
      <h2 className="cobre-section-title">
        Métricas por Grupo{" "}
        <small className="cobre-muted cobre-section-hint">
          (clique para filtrar)
        </small>
      </h2>
      <div className="cobre-metrics-grid">
        {groups.map(([group, g]) => {
          const active = group === selectedGroup;
          return (
            <button
              key={group}
              type="button"
              className="cobre-metrics-card cobre-metrics-card-button"
              data-active={active}
              aria-pressed={active}
              onClick={() => onSelectGroup(active ? null : group)}
            >
              <h4 className="cobre-metrics-card-title">{group}</h4>
              <div className="cobre-metric-row">
                <span className="cobre-muted">Total</span>
                <span>{g.total ?? 0}</span>
              </div>
              <div className="cobre-metric-row">
                <span className="cobre-muted">Pass Rate</span>
                <span>{n(g.pct_pass).toFixed(1)}%</span>
              </div>
              <div className="cobre-metric-row">
                <span className="cobre-muted">MCP Used</span>
                <span>{n(g.pct_mcp_used).toFixed(1)}%</span>
              </div>
              <div className="cobre-metric-row">
                <span className="cobre-muted">Correct Tool</span>
                <span>{n(g.pct_correct_tool).toFixed(1)}%</span>
              </div>
              <div className="cobre-metric-row">
                <span className="cobre-muted">Avg Latency</span>
                <span>{n(g.avg_latency_ms).toFixed(0)}ms</span>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
