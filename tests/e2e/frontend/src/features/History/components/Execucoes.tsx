import { SEM_DADO, limparCaminhos, type Registro } from "@/data/rodada";

interface Props {
  registros: Registro[];
  titulo: string;
}

/** Cada execução: estado, duração e as tools que o agente chamou. */
export function Execucoes({ registros, titulo }: Props) {
  if (registros.length === 0) return <p className="nm-no-data">Nenhuma execução neste conjunto</p>;
  return (
    <section className="nm-panel" aria-label={titulo}>
      <h2 className="nm-panel-title">{titulo}</h2>
      <div className="nm-table-scroll">
        <table className="nm-table">
          <thead>
            <tr>
              <th>caso</th>
              <th>agente</th>
              <th>config</th>
              <th>rep.</th>
              <th>estado</th>
              <th>duração (s)</th>
              <th>tools</th>
              <th>motivo</th>
            </tr>
          </thead>
          <tbody>
            {registros.map((r) => (
              <tr key={`${r.caso}/${r.agente}/${r.config}/${r.repeticao}`}>
                <td>{r.caso}</td>
                <td>{r.agente}</td>
                <td>{r.config}</td>
                <td>{r.repeticao}</td>
                <td>{r.estado}</td>
                <td>{r.duracao_s.toFixed(2)}</td>
                <td>{r.tools.length > 0 ? r.tools.map((t) => t.nome).join(", ") : SEM_DADO}</td>
                <td>{r.motivo ? limparCaminhos(r.motivo) : SEM_DADO}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
