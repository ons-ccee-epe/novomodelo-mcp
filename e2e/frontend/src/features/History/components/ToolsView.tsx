import { useMemo, useState } from "react";

import {
  AVISOS_DE_TOOLS,
  loteDeTools,
  opcoesDeTools,
  type ResumoRodada,
  type Rodada,
} from "@/data/rodada";
import { useRodadasCompletas } from "@/services/api/useRodadas";
import { BatchDashboard } from "./BatchDashboard";

const MAX_RODADAS_ANTERIORES = 8;

interface Props {
  rodada: Rodada;
  todas: ResumoRodada[];
}

/** As telas do conjunto tools: um lote por configuração e agente, com gráficos e perguntas. */
export function ToolsView({ rodada, todas }: Props) {
  const { configs, agentes } = useMemo(() => opcoesDeTools(rodada.registros), [rodada.registros]);
  const [escolhidaConfig, setConfig] = useState<string | null>(null);
  const [escolhidoAgente, setAgente] = useState<string | null>(null);
  const config = escolhidaConfig && configs.includes(escolhidaConfig) ? escolhidaConfig : configs[0];
  const agente = escolhidoAgente && agentes.includes(escolhidoAgente) ? escolhidoAgente : agentes[0];

  const outras = useMemo(
    () =>
      config && agente
        ? todas
            .filter(
              (r) =>
                r.rodada !== rodada.rodada &&
                !r.erro &&
                (r.configs ?? []).includes(config) &&
                (r.agentes ?? []).includes(agente) &&
                (r.conjuntos ?? []).includes("tools"),
            )
            .slice(0, MAX_RODADAS_ANTERIORES)
            .map((r) => r.rodada)
        : [],
    [todas, rodada.rodada, config, agente],
  );
  const anteriores = useRodadasCompletas(outras);
  const lote = useMemo(
    () => (config && agente ? loteDeTools(rodada, config, agente) : null),
    [rodada, config, agente],
  );
  const doutras = useMemo(
    () =>
      config && agente
        ? anteriores.rodadas
            .map((r) => loteDeTools(r, config, agente))
            .filter((l) => l.test_results.length > 0)
        : [],
    [anteriores.rodadas, config, agente],
  );

  if (!lote || !config || !agente) {
    return <p className="nm-no-data">Nenhuma execução neste conjunto</p>;
  }

  const avisos = [...AVISOS_DE_TOOLS];
  if (anteriores.loading) avisos.push("Carregando as rodadas anteriores para a evolução…");
  if (anteriores.falhas > 0) {
    avisos.push(`${anteriores.falhas} rodada(s) anterior(es) não puderam ser lidas e ficaram fora da evolução.`);
  }
  if (outras.length === MAX_RODADAS_ANTERIORES) {
    avisos.push(`A evolução usa só as ${MAX_RODADAS_ANTERIORES} rodadas anteriores mais recentes.`);
  }

  return (
    <>
      <div className="nm-form-row">
        <div className="nm-field">
          <label className="nm-field-label" htmlFor="tools-config">
            Configuração
          </label>
          <select
            id="tools-config"
            className="nm-select"
            value={config}
            onChange={(e) => setConfig(e.target.value)}
          >
            {configs.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div className="nm-field">
          <label className="nm-field-label" htmlFor="tools-agente">
            Agente
          </label>
          <select
            id="tools-agente"
            className="nm-select"
            value={agente}
            onChange={(e) => setAgente(e.target.value)}
          >
            {agentes.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
      </div>
      <BatchDashboard key={`${config}/${agente}`} batch={lote} all={[lote, ...doutras]} avisos={avisos} />
    </>
  );
}
