import type { LoadResources, LoadRun, LoadSandbox } from "@/shared/types";
import { fmtMb, fmtMbFine, fmtMs, fmtSeconds } from "../format";

interface Props {
  run: LoadRun;
}

export function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="cobre-metric-row">
      <span className="cobre-muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}

/**
 * "Cópia por sessão: X MB (subárvores ...), cópia em ~Y ms". Nada quando o registro não tem
 * sandbox (JSONs antigos) ou ele estava desligado.
 */
export function SandboxRow({ sandbox }: { sandbox?: LoadSandbox }) {
  if (!sandbox?.enabled) return null;
  const parts: string[] = [];
  const size = typeof sandbox.copy_mb === "number" ? fmtMbFine(sandbox.copy_mb) : null;
  const trees =
    sandbox.subtrees && sandbox.subtrees.length > 0
      ? `subárvores: ${sandbox.subtrees.join(", ")}`
      : null;
  if (size && trees) parts.push(`${size} (${trees})`);
  else if (size) parts.push(size);
  else if (trees) parts.push(trees);
  if (typeof sandbox.copy_ms_mean === "number") {
    const max = typeof sandbox.copy_ms_max === "number" ? ` (máx ${fmtMs(sandbox.copy_ms_max)})` : "";
    parts.push(`cópia em ~${fmtMs(sandbox.copy_ms_mean)}${max}`);
  }
  return <Row label="Cópia por sessão" value={parts.length > 0 ? parts.join(", ") : "ativada"} />;
}

function ConfigCard({ run }: Props) {
  const c = run.config;
  return (
    <div className="cobre-metrics-card">
      <h4>Configuração</h4>
      <Row label="Sessões simultâneas" value={String(c.concurrency)} />
      <Row label="Duração pedida" value={`${c.duration_seconds} s`} />
      <Row label="Iterações por sessão" value={c.iterations === null ? "sem limite" : String(c.iterations)} />
      <Row label="Timeout por chamada" value={`${c.timeout_seconds} s`} />
      <Row label="Tools" value={c.tools ? `${c.tools.length} escolhida(s)` : "mix padrão"} />
      <SandboxRow sandbox={run.sandbox} />
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
      <Row label="Sessões abertas" value={`${s.started}/${s.clients}`} />
      <Row label="Tempo até todas prontas" value={fmtSeconds(s.wall_ms / 1000)} />
      <Row label="Por sessão (mín / méd / máx)" value={`${fmtMs(s.min_ms)} / ${fmtMs(s.mean_ms)} / ${fmtMs(s.max_ms)}`} />
      <Row label="Aquecimento médio" value={fmtMs(s.warmup_mean_ms)} />
      <Row label="Pré-voo" value={fmtMs(s.preflight_ms)} />
      <Row label="Sessões recriadas" value={String(s.respawns)} />
    </div>
  );
}

/** CPU e RSS somados dos processos da carga (``title`` nomeia quais são). */
export function ResourcesCard({
  resources: r,
  title = "Recursos dos servidores",
}: {
  resources: LoadResources;
  title?: string;
}) {
  const measured = r.available && (r.samples?.length ?? 0) > 0;
  return (
    <div className="cobre-metrics-card">
      <h4>{title}</h4>
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
        <ResourcesCard resources={run.resources} />
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
