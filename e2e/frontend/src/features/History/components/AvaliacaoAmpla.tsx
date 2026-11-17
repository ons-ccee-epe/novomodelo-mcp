import {
  INTRO_AMPLA,
  METRICAS_AMPLAS,
  avaliacaoAmpla,
  type Registro,
} from "@/data/rodada";

interface Props {
  registros: Registro[];
}

/** Médias por conversa do conjunto usuário, por agente, com as configurações lado a lado. */
export function AvaliacaoAmpla({ registros }: Props) {
  const agentes = avaliacaoAmpla(registros);
  if (agentes.length === 0) return null;
  const conversas = agentes.reduce(
    (total, a) => total + a.resumo.reduce((n, l) => n + l.n, 0),
    0,
  );

  return (
    <section className="nm-panel" aria-label="Avaliação ampla">
      <h2 className="nm-panel-title">Avaliação ampla — {conversas} conversas</h2>
      <p className="nm-muted">{INTRO_AMPLA}</p>
      {agentes.map((a) => (
        <div key={a.agente} className="nm-section">
          <h3 className="nm-section-title">{a.agente}: resumo</h3>
          <div className="nm-table-scroll">
            <table className="nm-table" aria-label={`${a.agente}: resumo`}>
              <thead>
                <tr>
                  <th>condição</th>
                  <th>n</th>
                  {METRICAS_AMPLAS.map(([chave, nome]) => (
                    <th key={chave}>{nome}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.resumo.map((linha) => (
                  <tr key={linha.config}>
                    <td>{linha.config}</td>
                    <td>{linha.n}</td>
                    {linha.valores.map((v, i) => (
                      <td key={METRICAS_AMPLAS[i]![0]}>{v}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3 className="nm-section-title">
            {a.agente}: por cenário (uso da tool / nota / interrupções / tempo)
          </h3>
          <div className="nm-table-scroll">
            <table className="nm-table" aria-label={`${a.agente}: por cenário`}>
              <thead>
                <tr>
                  <th>cenário</th>
                  {a.configs.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.cenarios.map((c) => (
                  <tr key={c.caso}>
                    <td>{c.caso}</td>
                    {c.celulas.map((celula, i) => (
                      <td key={a.configs[i]}>{celula}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
