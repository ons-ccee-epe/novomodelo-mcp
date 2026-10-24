import { useMemo } from "react";

import type { LoadRun } from "@/shared/types";
import { compareStats, compareToolP95, configDifferences, type MetricDelta } from "../compare";
import { fmtLoadId, fmtMs, fmtPercent, fmtRate } from "../format";

interface Props {
  current: LoadRun;
  previous: LoadRun;
}

/** A seta mostra para onde o valor andou; a cor (data-trend) diz se isso é melhor ou pior. */
function arrowOf(delta: number | null): string {
  if (delta === null || delta === 0) return "→";
  return delta > 0 ? "↑" : "↓";
}

function formatValue(key: MetricDelta["spec"]["key"], value: number | null): string {
  if (key === "throughput_cps") return fmtRate(value);
  if (key === "error_rate") return fmtPercent(value);
  return fmtMs(value);
}

function formatDelta(d: MetricDelta): string {
  if (d.delta === null) return "sem dados";
  if (d.delta === 0) return "0";
  const sign = d.delta > 0 ? "+" : "-";
  const magnitude =
    d.spec.key === "error_rate"
      ? `${(Math.abs(d.delta) * 100).toFixed(1)} p.p.`
      : formatValue(d.spec.key, Math.abs(d.delta));
  const relative = d.relative !== null ? ` (${sign}${Math.abs(d.relative * 100).toFixed(0)}%)` : "";
  return `${sign}${magnitude}${relative}`;
}

/** Compara a carga selecionada com outra (por padrão, a anterior): vazão, erro e latência. */
export function LoadComparison({ current, previous }: Props) {
  const metrics = useMemo(() => compareStats(current.totals, previous.totals), [current, previous]);
  const tools = useMemo(() => compareToolP95(current, previous), [current, previous]);
  const differences = useMemo(
    () => configDifferences(current.config, previous.config),
    [current, previous],
  );

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
        <table className="cobre-table cobre-load-compare-table" aria-label="p95 por tool">
          <thead>
            <tr>
              <th>Tool</th>
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
