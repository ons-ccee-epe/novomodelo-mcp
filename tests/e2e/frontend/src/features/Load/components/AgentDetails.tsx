import type { AgentLoadRun } from "@/shared/types";
import { fmtSeconds } from "../format";
import { ResourcesCard, Row, SandboxRow } from "./LoadDetails";

interface Props {
  run: AgentLoadRun;
}

function ConfigCard({ run }: Props) {
  const c = run.config;
  const denied = run.agent.denied_tools;
  return (
    <div className="cobre-metrics-card">
      <h4>Configuração</h4>
      <Row label="Provedor" value={`${run.agent.label} (${run.agent.binary})`} />
      <Row label="Sessões simultâneas" value={String(c.concurrency)} />
      <Row label="Duração pedida" value={`${c.duration_seconds} s`} />
      <Row
        label="Iterações por sessão"
        value={c.iterations === null ? "sem limite" : String(c.iterations)}
      />
      <Row
        label="Timeout por caso"
        value={c.timeout_seconds === null ? "o de cada caso" : `${c.timeout_seconds} s`}
      />
      <Row label="Casos" value={run.cases.selection} />
      <SandboxRow sandbox={run.sandbox} />
      <Row
        label="Tools de escrita negadas"
        value={denied.length > 0 ? String(denied.length) : "nenhuma"}
      />
      <Row label="Versão do MCP" value={run.version} />
      <Row label="Commit" value={run.git_commit_sha.slice(0, 7)} />
    </div>
  );
}

function SessionsCard({ run }: Props) {
  const s = run.sessions;
  return (
    <div className="cobre-metrics-card">
      <h4>Sessões</h4>
      <div className="cobre-muted cobre-load-note">
        O preparo (pré-voo e subida) é medido à parte e não entra na latência dos casos.
      </div>
      <Row label="Sessões preparadas" value={`${s.started}/${s.requested}`} />
      <Row label="Sessões que falharam" value={String(s.failed)} />
      <Row label="Tempo de preparo" value={fmtSeconds(s.setup_ms / 1000)} />
    </div>
  );
}

/** Configuração, sessões, recursos, erros agrupados e casos fora da carga do modo agente. */
export function AgentDetails({ run }: Props) {
  const { excluded } = run.cases;
  const failedSessions = run.sessions.events.filter((e) => !e.ok);
  const denied = run.agent.denied_tools;
  return (
    <>
      {run.interrupted && (
        <div className="cobre-banner" data-kind="warning">
          Carga interrompida antes do fim: o resultado é parcial.
        </div>
      )}
      {run.abandoned_calls > 0 && (
        <div className="cobre-banner" data-kind="warning">
          {run.abandoned_calls} caso(s) sem resposta foram abandonados ao fim da janela e não entram
          nas métricas.
        </div>
      )}
      <details className="cobre-section cobre-load-details" aria-label="Detalhes da carga">
        <summary>Detalhes</summary>
        <div className="cobre-load-details-body">
          <div className="cobre-metrics-grid">
            <ConfigCard run={run} />
            <SessionsCard run={run} />
            <ResourcesCard resources={run.resources} title="Recursos (agentes + servidores)" />
          </div>

          {failedSessions.length > 0 && (
            <details className="cobre-load-excluded">
              <summary className="cobre-summary-toggle">
                Sessões que falharam ({failedSessions.length})
              </summary>
              <ul className="cobre-tool-call-list">
                {failedSessions.map((e) => (
                  <li key={e.session}>
                    sessão {e.session} — {e.error ?? "falha sem mensagem"}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {denied.length > 0 && (
            <details className="cobre-load-excluded">
              <summary className="cobre-summary-toggle">
                Tools de escrita negadas ao claude ({denied.length})
              </summary>
              <ul className="cobre-tool-call-list">
                {denied.map((tool) => (
                  <li key={tool}>
                    <code>{tool}</code>
                  </li>
                ))}
              </ul>
            </details>
          )}

          {run.errors.length > 0 && (
            <>
              <h3 className="cobre-load-subtitle">Erros e timeouts por caso</h3>
              <table className="cobre-table" aria-label="Erros agrupados">
                <thead>
                  <tr>
                    <th>Caso</th>
                    <th>Status</th>
                    <th>Tipo</th>
                    <th>Mensagem</th>
                    <th>Ocorrências</th>
                  </tr>
                </thead>
                <tbody>
                  {run.errors.map((e) => (
                    <tr key={`${e.case_id}-${e.status}-${e.outcome}-${e.message}`}>
                      <td>
                        <code>{e.case_id}</code>
                      </td>
                      <td>{e.status}</td>
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
                Casos fora da carga ({excluded.length})
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
        </div>
      </details>
    </>
  );
}
