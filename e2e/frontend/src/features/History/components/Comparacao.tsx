import { useState } from "react";

import { comparar, type ResumoRodada, type Rodada } from "@/data/rodada";
import { useRodada } from "@/services/api/useRodadas";

const ROTULO = { regressao: "regressão", melhora: "melhora", mudanca: "mudança" } as const;
const TOM = { regressao: "fail", melhora: "pass", mudanca: "partial" } as const;

interface Props {
  atual: Rodada;
  outras: ResumoRodada[];
}

/** Casos cujo estado mudou da rodada escolhida para a aberta; as regressões vêm primeiro. */
export function Comparacao({ atual, outras }: Props) {
  const [baseId, setBaseId] = useState<string | null>(null);
  const base = useRodada(baseId);
  const candidatas = outras.filter((r) => r.rodada !== atual.rodada && !r.erro);
  const difs = base.rodada ? comparar(base.rodada, atual) : [];

  return (
    <section className="nm-panel" aria-label="Comparação com outra rodada">
      <h2 className="nm-panel-title">Comparação com outra rodada</h2>
      <div className="nm-field">
        <label className="nm-field-label" htmlFor="rodada-base">
          Rodada de referência
        </label>
        <select
          id="rodada-base"
          className="nm-select"
          value={baseId ?? ""}
          onChange={(e) => setBaseId(e.target.value || null)}
        >
          <option value="">Nenhuma</option>
          {candidatas.map((r) => (
            <option key={r.rodada} value={r.rodada}>
              {r.rodada}
            </option>
          ))}
        </select>
      </div>
      {base.loading && <p className="nm-muted">Carregando a rodada de referência…</p>}
      {base.error && (
        <div className="nm-banner" data-kind="critical" role="alert">
          {base.error}
        </div>
      )}
      {base.rodada && difs.length === 0 && (
        <p className="nm-muted">Nenhuma diferença de estado entre as rodadas.</p>
      )}
      {difs.length > 0 && (
        <div className="nm-table-scroll">
          <table className="nm-table" aria-label="Diferenças de estado">
            <thead>
              <tr>
                <th>Variação</th>
                <th>Conjunto</th>
                <th>Agente</th>
                <th>Config</th>
                <th>Caso</th>
                <th>Antes</th>
                <th>Depois</th>
              </tr>
            </thead>
            <tbody>
              {difs.map((d) => (
                <tr key={`${d.conjunto}/${d.agente}/${d.config}/${d.caso}`}>
                  <td>
                    <span className="nm-pill" data-tone={TOM[d.tipo]}>
                      {ROTULO[d.tipo]}
                    </span>
                  </td>
                  <td>{d.conjunto}</td>
                  <td>{d.agente}</td>
                  <td>{d.config}</td>
                  <td>{d.caso}</td>
                  <td>{d.antes}</td>
                  <td>{d.depois}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
