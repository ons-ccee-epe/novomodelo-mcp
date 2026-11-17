import type { Registro } from "@/data/rodada";

interface Props {
  registros: Registro[];
}

/** Quantas execuções terminaram em cada estado, por conjunto, agente e configuração. */
export function Taxas({ registros }: Props) {
  const grupos = new Map<string, Registro[]>();
  for (const r of registros) {
    const chave = JSON.stringify([r.conjunto, r.agente, r.config]);
    grupos.set(chave, [...(grupos.get(chave) ?? []), r]);
  }
  if (grupos.size === 0) return null;
  const contar = (rs: Registro[], estado: Registro["estado"]) =>
    rs.filter((r) => r.estado === estado).length;

  return (
    <section className="nm-panel" aria-label="Execuções por estado">
      <h2 className="nm-panel-title">Execuções por estado</h2>
      <div className="nm-table-scroll">
        <table className="nm-table">
          <thead>
            <tr>
              <th>Conjunto</th>
              <th>Agente</th>
              <th>Config</th>
              <th>Passou</th>
              <th>Falhou</th>
              <th>Pulado</th>
              <th>Erro infra</th>
            </tr>
          </thead>
          <tbody>
            {[...grupos.entries()].map(([chave, rs]) => {
              const [conjunto, agente, config] = JSON.parse(chave) as [string, string, string];
              return (
                <tr key={chave}>
                  <td>{conjunto}</td>
                  <td>{agente}</td>
                  <td>{config}</td>
                  <td>{contar(rs, "passou")}</td>
                  <td>{contar(rs, "falhou")}</td>
                  <td>{contar(rs, "pulado")}</td>
                  <td>{contar(rs, "erro_infra")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
