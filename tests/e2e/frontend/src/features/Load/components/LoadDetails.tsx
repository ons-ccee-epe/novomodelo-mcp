import type { LoadRun } from "@/shared/types";
import { fmtMb, fmtMs, fmtSeconds } from "../format";

interface Props {
  run: LoadRun;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="cobre-metric-row">
      <span className="cobre-muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function ConfigCard({ run }: Props) {
  const c = run.config;
  return (
    <div className="cobre-metrics-card">
      <h4>Configuração</h4>
      <Row label="Clientes" value={String(c.concurrency)} />
      <Row label="Duração pedida" value={`${c.duration_seconds} s`} />
      <Row label="Iterações por cliente" value={c.iterations === null ? "sem limite" : String(c.iterations)} />
      <Row label="Timeout por chamada" value={`${c.timeout_seconds} s`} />
      <Row label="Tools" value={c.tools ? `${c.tools.length} escolhida(s)` : "mix inteiro"} />
      <Row label="Versão do MCP" value={run.version} />
      <Row label="Commit" value={run.git_commit_sha.slice(0, 7)} />
    </div>
  );
}

function StartupCard({ run }: Props) {
  const s = run.startup;
  return (
    <div className="cobre-metrics-card">
      <h4>Subida dos servidores</h4>
      <div className="cobre-muted cobre-load-note">Medida à parte: não entra na latência das chamadas.</div>
      <Row label="Clientes iniciados" value={`${s.started}/${s.clients}`} />
      <Row label="Tempo até todos prontos" value={fmtSeconds(s.wall_ms / 1000)} />
      <Row label="Por cliente (mín / méd / máx)" value={`${fmtMs(s.min_ms)} / ${fmtMs(s.mean_ms)} / ${fmtMs(s.max_ms)}`} />
      <Row label="Aquecimento médio" value={fmtMs(s.warmup_mean_ms)} />
      <Row label="Pré-voo" value={fmtMs(s.preflight_ms)} />
      <Row label="Clientes recriados" value={String(s.respawns)} />
    </div>
  );
}

function ResourcesCard({ run }: Props) {
  const r = run.resources;
  const measured = r.available && (r.samples?.length ?? 0) > 0;
  return (
    <div className="cobre-metrics-card">
      <h4>Recursos dos servidores</h4>
      {measured ? (
        <>
          <Row label="CPU média (soma)" value={`${(r.avg_cpu_percent ?? 0).toFixed(0)}%`} />
          <Row label="CPU de pico" value={`${(r.peak_cpu_percent ?? 0).toFixed(0)}%`} />
          <Row label="RSS de pico" value={fmtMb(r.peak_rss_mb)} />
          <Row label="Processos de pico" value={String(r.peak_processes ?? "—")} />
        </>
      ) : (
        <div className="cobre-muted cobre-load-note">
          CPU e RSS não medidos{r.reason ? ` (${r.reason})` : ""}.
        </div>
      )}
    </div>
  );
}

/** Configuração, subida, recursos, chamadas fora do mix e erros agrupados da carga. */
export function LoadDetails({ run }: Props) {
  const excluded = run.mix.excluded;
  return (
    <section className="cobre-section" aria-label="Detalhes da carga">
      <h2 className="cobre-section-title">Detalhes</h2>
      {run.interrupted && (
        <div className="cobre-banner" data-kind="warning">
          Carga interrompida antes do fim: o resultado é parcial.
        </div>
      )}
      {run.abandoned_calls > 0 && (
        <div className="cobre-banner" data-kind="warning">
          {run.abandoned_calls} chamada(s) sem resposta foram abandonadas ao fim da janela e não
          entram nas métricas.
        </div>
      )}
      <div className="cobre-metrics-grid">
        <ConfigCard run={run} />
        <StartupCard run={run} />
        <ResourcesCard run={run} />
      </div>

      {run.errors.length > 0 && (
        <>
          <h3 className="cobre-load-subtitle">Erros e timeouts</h3>
          <table className="cobre-table" aria-label="Erros agrupados">
            <thead>
              <tr>
                <th>Tool</th>
                <th>Tipo</th>
                <th>Mensagem</th>
                <th>Ocorrências</th>
              </tr>
            </thead>
            <tbody>
              {run.errors.map((e) => (
                <tr key={`${e.tool}-${e.outcome}-${e.message}`}>
                  <td>
                    <code>{e.tool}</code>
                  </td>
                  <td>{e.outcome}</td>
                  <td>{e.message}</td>
                  <td>{e.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {excluded.length > 0 && (
        <details className="cobre-load-excluded">
          <summary className="cobre-summary-toggle">
            Chamadas fora do mix ({excluded.length})
          </summary>
          <ul className="cobre-tool-call-list">
            {excluded.map((item) => (
              <li key={item.id}>
                <code>{item.id}</code> — {item.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
