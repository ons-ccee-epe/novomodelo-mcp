import { useState } from "react";

import {
  CONJUNTOS,
  ROTULO_CONJUNTO,
  limparCaminhos,
  type Conjunto,
  type ResumoRodada,
  type Rodada,
} from "@/data/rodada";
import { formatDate } from "../format";
import { AvaliacaoAmpla } from "./AvaliacaoAmpla";
import { Comparacao } from "./Comparacao";
import { Configuracoes } from "./Configuracoes";
import { Execucoes } from "./Execucoes";
import { GoNoGo } from "./GoNoGo";
import { NotasDoJuiz } from "./NotasDoJuiz";
import { Taxas } from "./Taxas";
import { ToolsView } from "./ToolsView";

interface Props {
  rodada: Rodada;
  todas: ResumoRodada[];
}

const ORDEM_INICIAL: Conjunto[] = ["usuario", "tools", "deterministica"];

/** Tudo de uma rodada: veredito e configurações no topo, o conjunto escolhido e a comparação. */
export function RodadaDashboard({ rodada, todas }: Props) {
  const m = rodada.manifesto;
  const [escolhido, setEscolhido] = useState<Conjunto | null>(null);
  const conjunto =
    escolhido ?? ORDEM_INICIAL.find((c) => rodada.registros.some((r) => r.conjunto === c)) ?? "usuario";
  const doConjunto = rodada.registros.filter((r) => r.conjunto === conjunto);

  return (
    <section className="nm-batch-dashboard" aria-label="Dashboard da rodada">
      <header className="nm-batch-header">
        <h2 className="nm-batch-title">{rodada.rodada}</h2>
        <p className="nm-muted">
          {rodada.criado_em ? formatDate(rodada.criado_em) : "—"}
          {rodada.commit_bateria ? ` · bateria ${rodada.commit_bateria}` : ""}
          {rodada.repeticoes ? ` · ${rodada.repeticoes} repetição(ões)` : ""}
        </p>
        {rodada.em_andamento && (
          <span className="nm-pill" data-tone="running">
            em andamento
          </span>
        )}
        {rodada.bloqueada && (
          <span className="nm-pill" data-tone="fail">
            bloqueada
          </span>
        )}
      </header>
      {rodada.erro && (
        <div className="nm-banner" data-kind="critical" role="alert">
          {limparCaminhos(rodada.erro)}
        </div>
      )}
      <GoNoGo decisao={rodada.go_no_go} />
      {m && <Configuracoes manifesto={m} />}
      <div className="nm-field">
        <label className="nm-field-label" htmlFor="filtro-conjunto">
          Conjunto
        </label>
        <select
          id="filtro-conjunto"
          className="nm-select"
          value={conjunto}
          onChange={(e) => setEscolhido(e.target.value as Conjunto)}
        >
          {CONJUNTOS.map((c) => (
            <option key={c} value={c}>
              {ROTULO_CONJUNTO[c]}
            </option>
          ))}
        </select>
      </div>
      {conjunto === "usuario" ? (
        <>
          <AvaliacaoAmpla registros={doConjunto} />
          <NotasDoJuiz registros={doConjunto} />
          {doConjunto.length === 0 && <p className="nm-no-data">Nenhuma execução neste conjunto</p>}
        </>
      ) : conjunto === "tools" ? (
        <ToolsView rodada={rodada} todas={todas} />
      ) : (
        <>
          <Taxas registros={doConjunto} />
          <Execucoes registros={doConjunto} titulo={`Execuções — ${ROTULO_CONJUNTO[conjunto]}`} />
        </>
      )}
      {m && <Comparacao atual={rodada} outras={todas} />}
    </section>
  );
}
