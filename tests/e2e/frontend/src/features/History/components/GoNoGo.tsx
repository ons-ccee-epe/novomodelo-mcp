import { limparCaminhos, type Decisao, type DecisaoComErro } from "@/data/rodada";

const TOM: Record<Decisao["veredito"], string> = {
  go: "pass",
  "no-go": "fail",
  inconclusivo: "partial",
};

interface Props {
  decisao: Decisao | DecisaoComErro | null;
}

function Lista({ titulo, itens }: { titulo: string; itens: string[] }) {
  if (itens.length === 0) return null;
  return (
    <p className="nm-muted">
      {titulo}: {itens.map(limparCaminhos).join(", ")}
    </p>
  );
}

/** O veredito que o go-no-go da CLI gravou, com os bloqueios e a evidência de cada um. */
export function GoNoGo({ decisao }: Props) {
  return (
    <section className="nm-panel" aria-label="Veredito do go-no-go">
      <h2 className="nm-panel-title">Veredito do go-no-go</h2>
      {decisao === null ? (
        <p className="nm-muted">go-no-go ainda não rodado</p>
      ) : "erro" in decisao ? (
        <div className="nm-banner" data-kind="critical" role="alert">
          {limparCaminhos(decisao.erro)}
        </div>
      ) : (
        <>
          <p>
            <span className="nm-pill" data-tone={TOM[decisao.veredito]}>
              {decisao.veredito}
            </span>{" "}
            alvo <code>{decisao.alvo}</code> · base{" "}
            {decisao.base ? <code>{limparCaminhos(decisao.base)}</code> : "sem base"}
          </p>
          <Lista titulo="Incompleto" itens={decisao.incompleto} />
          {decisao.bloqueios.length > 0 && (
            <ul className="nm-decisoes" aria-label="Bloqueios">
              {decisao.bloqueios.map((b) => (
                <li key={`${b.regra}/${b.conjunto}/${b.caso}/${b.agente}`}>
                  {b.conjunto} / {b.caso} / {b.agente} — {b.regra}
                  <ul>
                    {b.evidencia.map((e) => (
                      <li key={e}>
                        <code>{limparCaminhos(e)}</code>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
          <Lista titulo="Inconclusivos" itens={decisao.inconclusivos} />
          <Lista titulo="Pulados" itens={decisao.pulados} />
          <Lista titulo="Sem base" itens={decisao.sem_base} />
          <Lista titulo="Ausentes" itens={decisao.ausentes} />
        </>
      )}
    </section>
  );
}
