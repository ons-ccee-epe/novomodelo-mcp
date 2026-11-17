import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  comandoPrevio,
  dispararRodada,
  type EstadoDisparo,
  type PedidoRodada,
} from "@/data/rodada";
import { historyRodadaPath } from "@/shared/constants/Routes";

const CONJUNTOS_DISPARAVEIS = ["tools", "usuario"] as const;
const AGENTES = ["claude", "kiro"] as const;

function lista(texto: string): string[] {
  return texto
    .split(/[\s,]+/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function inteiro(texto: string): number | undefined {
  const n = Number.parseInt(texto, 10);
  return Number.isFinite(n) ? n : undefined;
}

interface Campos {
  rodada: string;
  semMcp: boolean;
  wheels: string;
  conjuntos: string[];
  agentes: string[];
  filtro: string;
  repeticoes: string;
  completa: boolean;
  maxExecucoes: string;
  maxMinutos: string;
  esperarLimite: string;
  paralelo: string;
}

const VAZIO: Campos = {
  rodada: "",
  semMcp: true,
  wheels: "",
  conjuntos: [],
  agentes: [],
  filtro: "",
  repeticoes: "",
  completa: false,
  maxExecucoes: "",
  maxMinutos: "",
  esperarLimite: "",
  paralelo: "",
};

/** Só os campos da lista branca de `POST /api/rodadas`; o que está vazio fica de fora. */
export function pedidoDosCampos(c: Campos): PedidoRodada {
  const pedido: PedidoRodada = { mcp: [...(c.semMcp ? ["sem"] : []), ...lista(c.wheels)] };
  if (c.rodada.trim()) pedido.rodada = c.rodada.trim();
  if (c.conjuntos.length) pedido.conjuntos = c.conjuntos as PedidoRodada["conjuntos"];
  if (c.agentes.length) pedido.agentes = c.agentes as PedidoRodada["agentes"];
  if (c.filtro.trim()) pedido.filtro = c.filtro.trim();
  if (c.completa) pedido.completa = true;
  const numeros: Array<[keyof PedidoRodada, string]> = [
    ["repeticoes", c.repeticoes],
    ["max_execucoes", c.maxExecucoes],
    ["max_minutos", c.maxMinutos],
    ["esperar_limite", c.esperarLimite],
    ["paralelo_por_agente", c.paralelo],
  ];
  for (const [chave, texto] of numeros) {
    const n = inteiro(texto);
    if (n !== undefined) Object.assign(pedido, { [chave]: n });
  }
  return pedido;
}

function alternar(lista: string[], valor: string): string[] {
  return lista.includes(valor) ? lista.filter((v) => v !== valor) : [...lista, valor];
}

/** Aba "Testes Funcionais": monta e dispara uma rodada da bateria pelo launcher. */
export function Functional() {
  const [campos, setCampos] = useState<Campos>(VAZIO);
  const [comando, setComando] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [estado, setEstado] = useState<EstadoDisparo | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const set = <K extends keyof Campos>(chave: K, valor: Campos[K]) =>
    setCampos((c) => ({ ...c, [chave]: valor }));
  const pedido = pedidoDosCampos(campos);

  useEffect(() => {
    if (pedido.mcp.length === 0) {
      setComando(null);
      setAviso(null);
      return;
    }
    let vivo = true;
    comandoPrevio(pedido)
      .then((c) => {
        if (!vivo) return;
        setComando(c.comando);
        setAviso(null);
      })
      .catch((e: unknown) => {
        if (!vivo) return;
        setComando(null);
        setAviso(e instanceof Error ? e.message : String(e));
      });
    return () => {
      vivo = false;
    };
    // O pedido é derivado de `campos`; depender dele cria um objeto novo a cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(pedido)]);

  async function disparar() {
    setOcupado(true);
    setErro(null);
    try {
      setEstado(await dispararRodada(pedido));
    } catch (e: unknown) {
      setErro(e instanceof Error ? e.message : String(e));
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="nm-shell">
      <section className="nm-panel nm-launcher" aria-label="Disparo da rodada">
        <h2 className="nm-panel-title">Disparar uma rodada</h2>
        <div className="nm-form-grid">
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-nome">
              Nome da rodada
            </label>
            <input
              id="rodada-nome"
              className="nm-input"
              value={campos.rodada}
              placeholder="gerado a partir da data"
              onChange={(e) => set("rodada", e.target.value)}
            />
          </div>
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-wheels">
              Wheels do MCP (nomes de arquivo)
            </label>
            <input
              id="rodada-wheels"
              className="nm-input"
              value={campos.wheels}
              onChange={(e) => set("wheels", e.target.value)}
            />
          </div>
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-filtro">
              Filtro dos casos
            </label>
            <input
              id="rodada-filtro"
              className="nm-input"
              value={campos.filtro}
              onChange={(e) => set("filtro", e.target.value)}
            />
          </div>
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-repeticoes">
              Repetições
            </label>
            <input
              id="rodada-repeticoes"
              className="nm-input"
              inputMode="numeric"
              value={campos.repeticoes}
              onChange={(e) => set("repeticoes", e.target.value)}
            />
          </div>
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-max-execucoes">
              Máximo de execuções
            </label>
            <input
              id="rodada-max-execucoes"
              className="nm-input"
              inputMode="numeric"
              value={campos.maxExecucoes}
              onChange={(e) => set("maxExecucoes", e.target.value)}
            />
          </div>
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-max-minutos">
              Máximo de minutos
            </label>
            <input
              id="rodada-max-minutos"
              className="nm-input"
              inputMode="numeric"
              value={campos.maxMinutos}
              onChange={(e) => set("maxMinutos", e.target.value)}
            />
          </div>
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-esperar">
              Esperar o limite de uso (minutos)
            </label>
            <input
              id="rodada-esperar"
              className="nm-input"
              inputMode="numeric"
              value={campos.esperarLimite}
              onChange={(e) => set("esperarLimite", e.target.value)}
            />
          </div>
          <div className="nm-field">
            <label className="nm-field-label" htmlFor="rodada-paralelo">
              Paralelo por agente
            </label>
            <input
              id="rodada-paralelo"
              className="nm-input"
              inputMode="numeric"
              value={campos.paralelo}
              onChange={(e) => set("paralelo", e.target.value)}
            />
          </div>
        </div>
        <div className="nm-form-row">
          <label className="nm-form-check">
            <input
              type="checkbox"
              checked={campos.semMcp}
              onChange={(e) => set("semMcp", e.target.checked)}
            />
            sem MCP
          </label>
          {CONJUNTOS_DISPARAVEIS.map((c) => (
            <label key={c} className="nm-form-check">
              <input
                type="checkbox"
                checked={campos.conjuntos.includes(c)}
                onChange={() => set("conjuntos", alternar(campos.conjuntos, c))}
              />
              {c === "usuario" ? "usuário" : c}
            </label>
          ))}
          {AGENTES.map((a) => (
            <label key={a} className="nm-form-check">
              <input
                type="checkbox"
                checked={campos.agentes.includes(a)}
                onChange={() => set("agentes", alternar(campos.agentes, a))}
              />
              {a}
            </label>
          ))}
          <label className="nm-form-check">
            <input
              type="checkbox"
              checked={campos.completa}
              onChange={(e) => set("completa", e.target.checked)}
            />
            completa
          </label>
        </div>
        {comando && (
          <p className="nm-muted">
            Comando equivalente: <code>{comando}</code>
          </p>
        )}
        {aviso && <p className="nm-muted">{aviso}</p>}
        {erro && (
          <div className="nm-banner" data-kind="critical" role="alert">
            {erro}
          </div>
        )}
        <div className="nm-form-actions">
          <button
            type="button"
            className="nm-btn nm-btn-primary"
            disabled={ocupado || pedido.mcp.length === 0}
            onClick={() => void disparar()}
          >
            Disparar rodada
          </button>
        </div>
        {estado && (
          <p role="status">
            Rodada <code>{estado.rodada}</code> {estado.status === "em_andamento" ? "em andamento" : "finalizada"}
            . <Link to={historyRodadaPath(estado.rodada)}>Ver no Histórico</Link>
          </p>
        )}
      </section>
    </div>
  );
}
