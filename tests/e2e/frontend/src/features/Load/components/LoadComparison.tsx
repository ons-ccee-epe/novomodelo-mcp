import { useMemo } from "react";

import { isAgentRun, type SavedLoadRun } from "@/shared/types";
import {
  AGENT_COMPARED_METRICS,
  compareCaseP95,
  compareStats,
  compareToolP95,
  configDifferences,
  type MetricDelta,
} from "../compare";
import { fmtCpm, fmtLoadId, fmtMs, fmtPercent, fmtRate } from "../format";

interface Props {
  current: SavedLoadRun;
  previous: SavedLoadRun;
}

/** A seta mostra para onde o valor andou; a cor (data-trend) diz se isso é melhor ou pior. */
function arrowOf(delta: number | null): string {
  if (delta === null || delta === 0) return "→";
  return delta > 0 ? "↑" : "↓";
}

function formatValue(key: MetricDelta["spec"]["key"], value: number | null): string {
  if (key === "throughput_cps") return fmtRate(value);
  if (key === "throughput_cpm") return fmtCpm(value);
  if (key === "error_rate" || key === "pass_rate") return fmtPercent(value);
  return fmtMs(value);
}

function formatDelta(d: MetricDelta): string {
  if (d.delta === null) return "sem dados";
  if (d.delta === 0) return "0";
  const sign = d.delta > 0 ? "+" : "-";
  const magnitude =
    d.spec.key === "error_rate" || d.spec.key === "pass_rate"
      ? `${(Math.abs(d.delta) * 100).toFixed(1)} p.p.`
      : formatValue(d.spec.key, Math.abs(d.delta));
  const relative = d.relative !== null ? ` (${sign}${Math.abs(d.relative * 100).toFixed(0)}%)` : "";
  return `${sign}${magnitude}${relative}`;
}

/**
 * Compara a carga selecionada com outra do mesmo modo (por padrão, a anterior): vazão,
 * erro e latência; no agente, também a aprovação e o p95 por caso.
 */
export function LoadComparison({ current, previous }: Props) {
  const agent = isAgentRun(current) && isAgentRun(previous);
  const sameMode = agent || (!isAgentRun(current) && !isAgentRun(previous));
  const metrics = useMemo(
    () =>
      sameMode
        ? compareStats(current.totals, previous.totals, agent ? AGENT_COMPARED_METRICS : undefined)
        : [],
    [current, previous, agent, sameMode],
  );
  const tools = useMemo(() => {
    if (!sameMode) return [];
    if (isAgentRun(current) && isAgentRun(previous)) return compareCaseP95(current, previous);
    if (!isAgentRun(current) && !isAgentRun(previous)) return compareToolP95(current, previous);
    return [];
  }, [current, previous, sameMode]);
  const differences = useMemo(
    () => configDifferences(current.config, previous.config),
    [current, previous],
  );

  if (!sameMode) return null;

  return (
    <section className="cobre-section" aria-label="Comparação entre cargas">
      <h2 className="cobre-section-title">
        Comparação: {fmtLoadId(current.load_id)} vs {fmtLoadId(previous.load_id)}
      </h2>
      {differences.length > 0 && (
        <div className="cobre-banner" data-kind="warning">
          As cargas usaram parâmetros diferentes ({differences.join(", ")}): a comparação é só
          indicativa.
        </div>
      )}
      <div className="cobre-metrics-grid">
        {metrics.map((m) => (
          <div key={m.spec.key} className="cobre-metrics-card">
            <h4>{m.spec.label}</h4>
            <span className="cobre-delta" data-trend={m.trend}>
              {arrowOf(m.delta)} {formatDelta(m)}
            </span>
            <div className="cobre-metric-row">
              <span className="cobre-muted">Agora</span>
              <span>{formatValue(m.spec.key, m.current)}</span>
            </div>
            <div className="cobre-metric-row">
              <span className="cobre-muted">Antes</span>
              <span>{formatValue(m.spec.key, m.previous)}</span>
            </div>
          </div>
        ))}
      </div>

      {tools.length > 0 && (
        <table className="cobre-table cobre-load-compare-table" aria-label={agent ? "p95 por caso" : "p95 por tool"}>
          <thead>
            <tr>
              <th>{agent ? "Caso" : "Tool"}</th>
              <th>p95 agora</th>
              <th>p95 antes</th>
              <th>Variação</th>
            </tr>
          </thead>
          <tbody>
            {tools.map((t) => (
              <tr key={t.tool}>
                <td>
                  <code>{t.tool}</code>
                </td>
                <td>{fmtMs(t.current)}</td>
                <td>{fmtMs(t.previous)}</td>
                <td>
                  <span className="cobre-load-trend" data-trend={t.trend}>
                    {arrowOf(t.delta)}{" "}
                    {t.delta === null
                      ? "—"
                      : `${t.delta > 0 ? "+" : t.delta < 0 ? "-" : ""}${fmtMs(Math.abs(t.delta))}`}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
