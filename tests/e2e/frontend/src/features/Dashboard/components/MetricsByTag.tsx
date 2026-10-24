import type { BatchResult } from "@/shared/types";

interface Props {
  batch: BatchResult;
}

function pct(n: number, total: number): string {
  return total > 0 ? `${((n / total) * 100).toFixed(1)}%` : "0.0%";
}

/** Metricas agregadas por tag. */
export function MetricsByTag({ batch }: Props) {
  const tags = Object.entries(batch.metrics_by_tag ?? {}).sort(([a], [b]) => a.localeCompare(b));

  if (tags.length === 0) {
    return (
      <section className="cobre-section">
        <h2 className="cobre-section-title">Métricas por Tag</h2>
        <div className="cobre-no-data">Nenhuma métrica por tag disponível</div>
      </section>
    );
  }

  return (
    <section className="cobre-section">
      <h2 className="cobre-section-title">Métricas por Tag</h2>
      <table className="cobre-table">
        <thead>
          <tr>
            <th>Tag</th>
            <th>Total</th>
            <th>Passed</th>
            <th>Failed</th>
            <th>Pass Rate</th>
            <th>MCP Used %</th>
            <th>Correct Tool %</th>
          </tr>
        </thead>
        <tbody>
          {tags.map(([tag, t]) => (
            <tr key={tag}>
              <td>
                <strong>{tag}</strong>
              </td>
              <td>{t.total}</td>
              <td>{t.passed}</td>
              <td>{t.failed}</td>
              <td>{pct(t.passed, t.total)}</td>
              <td>{pct(t.mcp_used, t.total)}</td>
              <td>{pct(t.correct_tool, t.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
