import { SEM_DADO, SEM_MCP, limparCaminhos, ordenarConfigs, type Manifesto } from "@/data/rodada";

const ROTULOS_DE_IMAGEM: Record<string, string> = {
  novomodelo: "novomodelo",
  "novomodelo-bridge": "bridge",
  "claude-code": "Claude Code",
  "kiro-cli": "Kiro",
};

interface Props {
  manifesto: Manifesto;
}

function colunasDeImagem(manifesto: Manifesto): string[] {
  const achadas = new Set(Object.values(manifesto.imagens).flatMap((v) => Object.keys(v)));
  const conhecidas = Object.keys(ROTULOS_DE_IMAGEM).filter((c) => achadas.has(c));
  const outras = [...achadas].filter((c) => !(c in ROTULOS_DE_IMAGEM)).sort();
  return [...conhecidas, ...outras];
}

/** Versão, SHA-256 e origem de cada wheel, as versões das imagens e os dados do juiz. */
export function Configuracoes({ manifesto }: Props) {
  const colunas = colunasDeImagem(manifesto);
  const imagens = Object.entries(manifesto.imagens).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));

  return (
    <section className="nm-panel" aria-label="Configurações">
      <h2 className="nm-panel-title">Configurações</h2>
      <div className="nm-table-scroll">
        <table className="nm-table" aria-label="Wheels por configuração">
          <thead>
            <tr>
              <th>Configuração</th>
              <th>Versão do MCP</th>
              <th>SHA-256 do wheel</th>
              <th>Origem</th>
            </tr>
          </thead>
          <tbody>
            {ordenarConfigs(manifesto.configs).map((config) => {
              const wheel = manifesto.wheels[config];
              const semMcp = config === SEM_MCP;
              return (
                <tr key={config}>
                  <td>{config}</td>
                  <td>{semMcp ? "sem MCP" : (manifesto.versoes[`mcp:${config}`] ?? SEM_DADO)}</td>
                  <td>{!semMcp && wheel?.sha256 ? <code>{wheel.sha256}</code> : SEM_DADO}</td>
                  <td>{!semMcp && wheel?.origem ? limparCaminhos(wheel.origem) : SEM_DADO}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {imagens.length > 0 && (
        <div className="nm-table-scroll">
          <table className="nm-table" aria-label="Imagens">
            <thead>
              <tr>
                <th>Imagem</th>
                {colunas.map((c) => (
                  <th key={c}>{ROTULOS_DE_IMAGEM[c] ?? c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {imagens.map(([tag, versoes]) => (
                <tr key={tag}>
                  <td>
                    <code>{tag}</code>
                  </td>
                  {colunas.map((c) => (
                    <td key={c}>{versoes[c] ?? SEM_DADO}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="nm-muted">
        Juiz: modelo {manifesto.versoes["juiz-modelo"] ?? SEM_DADO} · temperatura{" "}
        {manifesto.versoes["juiz-temperatura"] ?? SEM_DADO}.
      </p>
      <p className="nm-muted">
        Filtro da rodada: {manifesto.filtro ? <code>{limparCaminhos(manifesto.filtro)}</code> : "nenhum"}.
      </p>
    </section>
  );
}
