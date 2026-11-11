import { SEM_DADO, justificativaDoJuiz, ordenarConfigs, type Registro } from "@/data/rodada";

interface Props {
  registros: Registro[];
}

/** A nota e a justificativa do juiz em cada execução do conjunto usuário. */
export function NotasDoJuiz({ registros }: Props) {
  const rs = registros
    .filter((r) => r.conjunto === "usuario" && r.estado !== "pulado")
    .sort(
      (a, b) =>
        a.caso.localeCompare(b.caso) ||
        a.agente.localeCompare(b.agente) ||
        ordenarConfigs([a.config, b.config]).indexOf(a.config) -
          ordenarConfigs([a.config, b.config]).indexOf(b.config) ||
        a.repeticao - b.repeticao,
    );
  if (rs.length === 0) return null;
  return (
    <section className="nm-panel" aria-label="Notas e justificativas do juiz">
      <h2 className="nm-panel-title">Notas e justificativas do juiz</h2>
      <div className="nm-table-scroll">
        <table className="nm-table">
          <thead>
            <tr>
              <th>cenário</th>
              <th>agente</th>
              <th>condição</th>
              <th>rep.</th>
              <th>nota</th>
              <th>justificativa</th>
            </tr>
          </thead>
          <tbody>
            {rs.map((r) => (
              <tr key={`${r.caso}/${r.agente}/${r.config}/${r.repeticao}`}>
                <td>{r.caso}</td>
                <td>{r.agente}</td>
                <td>{r.config}</td>
                <td>{r.repeticao}</td>
                <td>{r.metricas.nota_juiz ?? SEM_DADO}</td>
                <td>{justificativaDoJuiz(r.motivo)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
