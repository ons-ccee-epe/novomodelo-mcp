/**
 * Fonte única dos dados das vistas: as rodadas da bateria, no formato dos schemas
 * `manifesto.schema.json` e `registro.schema.json`, lidas do launcher.
 *
 * As vistas só importam este módulo; nenhuma lê arquivo do disco.
 */
import { API, LAUNCHER_HEADERS } from "@/services/launcherApi";

export const SCHEMA_VERSAO = 1;
export const SEM_DADO = "—";
export const SEM_MCP = "sem-mcp";

export const CONJUNTOS = ["deterministica", "tools", "usuario"] as const;
export const ESTADOS = ["passou", "falhou", "pulado", "erro_infra"] as const;

export type Conjunto = (typeof CONJUNTOS)[number];
export type Estado = (typeof ESTADOS)[number];
export type Veredito = "go" | "no-go" | "inconclusivo";

export interface ChamadaTool {
  nome: string;
  ok: boolean | null;
  duracao_s: number | null;
}

export interface Metricas {
  acerto_tool: boolean | null;
  contornos: number | null;
  aprovacoes: number | null;
  rigidez: number | null;
  erros_envelope: number | null;
  t_primeira_tool: number | null;
  t_total: number | null;
  tokens_entrada: number | null;
  tokens_saida: number | null;
  resposta_correta: boolean | null;
  interrupcoes: number | null;
  t_primeira_interrupcao: number | null;
  maior_trecho_sem_interrupcao: number | null;
  indice_autonomia: number | null;
  comandos_terminal: number | null;
  nota_juiz: number | null;
}

export interface Registro {
  schema_versao: number;
  rodada: string;
  conjunto: Conjunto;
  caso: string;
  agente: string;
  config: string;
  repeticao: number;
  estado: Estado;
  motivo: string;
  tools: ChamadaTool[];
  duracao_s: number;
  metricas: Metricas;
}

export interface Wheel {
  arquivo: string;
  sha256: string;
  origem: string;
}

export interface Manifesto {
  schema_versao: number;
  rodada: string;
  criado_em: string;
  configs: string[];
  conjuntos: Conjunto[];
  agentes: string[];
  repeticoes: number;
  flags: Record<string, boolean>;
  versoes: Record<string, string>;
  commit_bateria: string;
  wheels: Record<string, Wheel>;
  imagens: Record<string, Record<string, string>>;
  filtro: string | null;
}

export interface Bloqueio {
  regra: "deterministica" | "regressao_tool" | "regressao_maioria";
  conjunto: string;
  caso: string;
  agente: string;
  evidencia: string[];
}

/** A decisão que o `go-no-go` da CLI grava na pasta da rodada. */
export interface Decisao {
  schema_versao: number;
  alvo: string;
  base: string | null;
  veredito: Veredito;
  bloqueios: Bloqueio[];
  inconclusivos: string[];
  pulados: string[];
  sem_base: string[];
  ausentes: string[];
}

export interface DecisaoComErro {
  erro: string;
}

export interface EstadoDisparo {
  rodada: string;
  status: "em_andamento" | "finalizada";
  iniciada_em: string;
  finalizada_em: string | null;
  codigo_saida: number | null;
  log: string;
  comando: string;
  log_bloqueado?: boolean;
}

export interface ResumoRodada {
  rodada: string;
  bloqueada: boolean;
  em_andamento: boolean;
  disparo: EstadoDisparo | null;
  erro: string | null;
  criado_em: string | null;
  configs: string[];
  conjuntos: Conjunto[];
  agentes: string[];
  repeticoes: number | null;
  filtro: string | null;
  commit_bateria: string | null;
}

export interface Rodada extends ResumoRodada {
  manifesto: Manifesto | null;
  registros: Registro[];
  /** `null`: o go-no-go ainda não rodou nesta rodada. */
  go_no_go: Decisao | DecisaoComErro | null;
}

/** As chaves exigem cada campo do tipo; o teste confere o conjunto contra o schema. */
export const CAMPOS_METRICAS: Record<keyof Metricas, true> = {
  acerto_tool: true,
  contornos: true,
  aprovacoes: true,
  rigidez: true,
  erros_envelope: true,
  t_primeira_tool: true,
  t_total: true,
  tokens_entrada: true,
  tokens_saida: true,
  resposta_correta: true,
  interrupcoes: true,
  t_primeira_interrupcao: true,
  maior_trecho_sem_interrupcao: true,
  indice_autonomia: true,
  comandos_terminal: true,
  nota_juiz: true,
};

export const CAMPOS_REGISTRO: Record<keyof Registro, true> = {
  schema_versao: true,
  rodada: true,
  conjunto: true,
  caso: true,
  agente: true,
  config: true,
  repeticao: true,
  estado: true,
  motivo: true,
  tools: true,
  duracao_s: true,
  metricas: true,
};

export const CAMPOS_MANIFESTO: Record<keyof Manifesto, true> = {
  schema_versao: true,
  rodada: true,
  criado_em: true,
  configs: true,
  conjuntos: true,
  agentes: true,
  repeticoes: true,
  flags: true,
  versoes: true,
  commit_bateria: true,
  wheels: true,
  imagens: true,
  filtro: true,
};

export class VersaoDesconhecida extends Error {
  constructor(mensagem: string) {
    super(mensagem);
    this.name = "VersaoDesconhecida";
  }
}

// ---- adaptadores --------------------------------------------------------

type Cru = Record<string, unknown>;

function objeto(valor: unknown, onde: string): Cru {
  if (valor === null || typeof valor !== "object" || Array.isArray(valor)) {
    throw new Error(`${onde}: esperado um objeto`);
  }
  return valor as Cru;
}

function conferir(dados: Cru, campos: Record<string, true>, onde: string): void {
  if (dados.schema_versao !== SCHEMA_VERSAO) {
    throw new VersaoDesconhecida(
      `${onde}: schema_versao ${String(dados.schema_versao)}, esta vista conhece ${SCHEMA_VERSAO}`,
    );
  }
  const faltam = Object.keys(campos).filter((c) => !(c in dados));
  if (faltam.length > 0) throw new Error(`${onde}: faltam os campos ${faltam.join(", ")}`);
}

export function adaptarManifesto(bruto: unknown): Manifesto {
  const dados = objeto(bruto, "manifesto");
  conferir(dados, CAMPOS_MANIFESTO, "manifesto");
  return dados as unknown as Manifesto;
}

export function adaptarRegistro(bruto: unknown): Registro {
  const dados = objeto(bruto, "registro");
  conferir(dados, CAMPOS_REGISTRO, "registro");
  const metricas = objeto(dados.metricas, "registro.metricas");
  const faltam = Object.keys(CAMPOS_METRICAS).filter((c) => !(c in metricas));
  if (faltam.length > 0) throw new Error(`registro.metricas: faltam os campos ${faltam.join(", ")}`);
  return dados as unknown as Registro;
}

function adaptarResumo(bruto: unknown): ResumoRodada {
  const d = objeto(bruto, "rodada");
  const lista = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
  return {
    rodada: String(d.rodada),
    bloqueada: d.bloqueada === true,
    em_andamento: d.em_andamento === true,
    disparo: (d.disparo as EstadoDisparo | null | undefined) ?? null,
    erro: typeof d.erro === "string" ? d.erro : null,
    criado_em: typeof d.criado_em === "string" ? d.criado_em : null,
    configs: lista<string>(d.configs),
    conjuntos: lista<Conjunto>(d.conjuntos),
    agentes: lista<string>(d.agentes),
    repeticoes: typeof d.repeticoes === "number" ? d.repeticoes : null,
    filtro: typeof d.filtro === "string" ? d.filtro : null,
    commit_bateria: typeof d.commit_bateria === "string" ? d.commit_bateria : null,
  };
}

// ---- rede ---------------------------------------------------------------

async function recusa(res: Response, prefixo: string): Promise<never> {
  let detalhe = `HTTP ${res.status}`;
  try {
    const corpo = (await res.json()) as { detail?: unknown };
    if (typeof corpo.detail === "string") detalhe = corpo.detail;
    else if (Array.isArray(corpo.detail)) {
      detalhe = corpo.detail
        .map((e) => (e && typeof e === "object" && "msg" in e ? String(e.msg) : String(e)))
        .join("; ");
    }
  } catch {
    /* corpo que não é JSON: fica o status */
  }
  throw new Error(`${prefixo}: ${detalhe}`);
}

export async function carregarRodadas(): Promise<ResumoRodada[]> {
  const res = await fetch(`${API}/rodadas`, { cache: "no-store" });
  if (!res.ok) return recusa(res, "Falha ao listar as rodadas");
  const corpo = objeto(await res.json(), "lista de rodadas");
  const itens = Array.isArray(corpo.rodadas) ? corpo.rodadas : [];
  return itens.map(adaptarResumo);
}

export async function carregarRodada(id: string): Promise<Rodada> {
  const res = await fetch(`${API}/rodadas/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!res.ok) return recusa(res, "Falha ao carregar a rodada");
  const corpo = objeto(await res.json(), "rodada");
  const registros = Array.isArray(corpo.registros) ? corpo.registros.map(adaptarRegistro) : [];
  return {
    ...adaptarResumo(corpo),
    manifesto: corpo.manifesto ? adaptarManifesto(corpo.manifesto) : null,
    registros,
    go_no_go: (corpo.go_no_go ?? null) as Rodada["go_no_go"],
  };
}

/** Os campos da lista branca de `POST /api/rodadas`. */
export interface PedidoRodada {
  rodada?: string;
  mcp: string[];
  conjuntos?: Array<"tools" | "usuario">;
  agentes?: Array<"claude" | "kiro">;
  filtro?: string;
  repeticoes?: number;
  completa?: boolean;
  max_execucoes?: number;
  max_minutos?: number;
  esperar_limite?: number;
  paralelo_por_agente?: number;
}

export async function dispararRodada(pedido: PedidoRodada): Promise<EstadoDisparo> {
  const res = await fetch(`${API}/rodadas`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...LAUNCHER_HEADERS },
    body: JSON.stringify(pedido),
  });
  if (!res.ok) return recusa(res, "Falha ao disparar a rodada");
  return (await res.json()) as EstadoDisparo;
}

export interface ComandoPrevio {
  comando: string;
  argumentos: string[];
}

export async function comandoPrevio(
  pedido: Omit<PedidoRodada, "rodada" | "max_execucoes" | "max_minutos" | "esperar_limite" | "paralelo_por_agente">,
): Promise<ComandoPrevio> {
  const params = new URLSearchParams();
  for (const m of pedido.mcp) params.append("mcp", m);
  if (pedido.conjuntos?.length) params.set("conjuntos", pedido.conjuntos.join(","));
  if (pedido.agentes?.length) params.set("agentes", pedido.agentes.join(","));
  if (pedido.filtro) params.set("filtro", pedido.filtro);
  if (pedido.repeticoes !== undefined) params.set("repeticoes", String(pedido.repeticoes));
  if (pedido.completa) params.set("completa", "true");
  const res = await fetch(`${API}/command-preview?${params.toString()}`, { cache: "no-store" });
  if (!res.ok) return recusa(res, "Falha ao montar o comando");
  return (await res.json()) as ComandoPrevio;
}

// ---- texto da tela ---------------------------------------------------------

export const ROTULO_CONJUNTO: Record<Conjunto, string> = {
  deterministica: "determinística",
  tools: "tools",
  usuario: "usuário",
};

const INICIO_CAMINHO = String.raw`(?:[A-Za-z]:[\\/]|\\\\|/(?!/))`;
const CAMINHO_ENTRE_ASPAS = new RegExp(`'${INICIO_CAMINHO}[^']*'|"${INICIO_CAMINHO}[^"]*"`, "g");
const CAMINHO_ABSOLUTO = new RegExp(String.raw`(?<![\w.~/\\-])${INICIO_CAMINHO}[^\s'"]*`, "g");

/** Troca caminhos absolutos (POSIX, Windows e UNC) por `<caminho>`, como a bateria faz nos relatórios. */
export function limparCaminhos(texto: string): string {
  return texto.replace(CAMINHO_ENTRE_ASPAS, "<caminho>").replace(CAMINHO_ABSOLUTO, "<caminho>");
}

/** A justificativa do juiz, que o `motivo` carrega depois do prefixo `juiz: `; sem prefixo, o motivo inteiro. */
export function justificativaDoJuiz(motivo: string): string {
  const achou = /(?:^|; )juiz: ([\s\S]*)$/.exec(motivo);
  return limparCaminhos(achou ? achou[1]! : motivo);
}

// ---- agrupamento e comparação -------------------------------------------

/**
 * Agrupa as rodadas pela configuração do MCP que rodaram (`mcp-<versão>` ou `sem-mcp`);
 * uma rodada com várias configurações aparece em cada uma. A configuração do próprio
 * checkout, que roda o conjunto determinístico, não é uma versão.
 */
export function porVersao<T extends ResumoRodada>(rodadas: T[]): Map<string, T[]> {
  const grupos = new Map<string, T[]>();
  for (const r of rodadas) {
    for (const config of ordenarConfigs(r.configs)) {
      if (config !== SEM_MCP && !config.startsWith("mcp-")) continue;
      grupos.set(config, [...(grupos.get(config) ?? []), r]);
    }
  }
  return new Map([...grupos.entries()].sort(([a], [b]) => comparaConfigs(a, b)));
}

export type EstadoDoCaso = Estado | "ausente";

export interface Diferenca {
  conjunto: string;
  caso: string;
  agente: string;
  config: string;
  antes: EstadoDoCaso;
  depois: EstadoDoCaso;
  tipo: "regressao" | "melhora" | "mudanca";
}

function estadoDoCaso(registros: Registro[]): EstadoDoCaso {
  const passou = registros.filter((r) => r.estado === "passou").length;
  const falhou = registros.filter((r) => r.estado === "falhou").length;
  if (passou + falhou > 0) return 2 * passou > passou + falhou ? "passou" : "falhou";
  if (registros.some((r) => r.estado === "erro_infra")) return "erro_infra";
  return registros.length > 0 ? "pulado" : "ausente";
}

function posto(estado: EstadoDoCaso): number {
  return estado === "passou" ? 2 : estado === "falhou" ? 1 : 0;
}

function agruparCasos(registros: Registro[]): Map<string, Registro[]> {
  const mapa = new Map<string, Registro[]>();
  for (const r of registros) {
    const chave = JSON.stringify([r.conjunto, r.caso, r.agente, r.config]);
    mapa.set(chave, [...(mapa.get(chave) ?? []), r]);
  }
  return mapa;
}

/** Casos cujo estado mudou de `a` para `b`, as regressões primeiro. */
export function comparar(a: Rodada, b: Rodada): Diferenca[] {
  const antes = agruparCasos(a.registros);
  const depois = agruparCasos(b.registros);
  const difs: Diferenca[] = [];
  for (const chave of new Set([...antes.keys(), ...depois.keys()])) {
    const [conjunto, caso, agente, config] = JSON.parse(chave) as [string, string, string, string];
    const de = estadoDoCaso(antes.get(chave) ?? []);
    const para = estadoDoCaso(depois.get(chave) ?? []);
    if (de === para) continue;
    const tipo = posto(para) < posto(de) ? "regressao" : posto(para) > posto(de) ? "melhora" : "mudanca";
    difs.push({ conjunto, caso, agente, config, antes: de, depois: para, tipo });
  }
  const ordem = { regressao: 0, mudanca: 1, melhora: 2 } as const;
  return difs.sort(
    (x, y) =>
      ordem[x.tipo] - ordem[y.tipo] ||
      x.conjunto.localeCompare(y.conjunto) ||
      x.agente.localeCompare(y.agente) ||
      x.caso.localeCompare(y.caso) ||
      x.config.localeCompare(y.config),
  );
}

// ---- avaliação ampla (mesmo formato e arredondamento do relatório) -------

export const METRICAS_AMPLAS = [
  ["acerto_tool", "uso da tool esperada (0–1)"],
  ["nota_juiz", "nota juiz (0–2)"],
  ["contornos", "contornos"],
  ["interrupcoes", "interrupções"],
  ["indice_autonomia", "autonomia"],
  ["t_total", "tempo (s)"],
  ["tokens_entrada", "tokens entrada"],
] as const satisfies ReadonlyArray<readonly [keyof Metricas, string]>;

export const POR_CENARIO = ["acerto_tool", "nota_juiz", "interrupcoes", "t_total"] as const;

export const INTRO_AMPLA =
  "Médias por conversa. Autonomia = fração do tempo até a 1ª interrupção (1 = nenhuma). " +
  "Interrupções = aprovações que a pessoa teria de dar. Nota do juiz: qualidade da resposta " +
  "(0, 1 ou 2). Uso da tool esperada: fração das conversas que chamaram as tools do MCP " +
  "previstas (sem MCP é ~0 por construção). Tempo: o do agente, medido no stream. " +
  `${SEM_DADO} = o agente não informa a métrica.`;

const PARTE_VERSAO = /[._+-]/;

type ParteDaChave = [number, number, string];
type ChaveDeConfig = [number, ParteDaChave[] | string];

function chaveDeConfig(config: string): ChaveDeConfig {
  if (config === SEM_MCP) return [0, []];
  if (config.startsWith("mcp-")) {
    const partes = config.slice("mcp-".length).split(PARTE_VERSAO);
    return [1, partes.map((p): ParteDaChave => (/^\d+$/.test(p) ? [0, Number(p), ""] : [1, 0, p]))];
  }
  return [2, config];
}

function comparaTexto(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function comparaPartes(a: ParteDaChave[], b: ParteDaChave[]): number {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    const [x, y] = [a[i]!, b[i]!];
    const d = x[0] - y[0] || x[1] - y[1] || comparaTexto(x[2], y[2]);
    if (d !== 0) return d;
  }
  return a.length - b.length;
}

function comparaConfigs(a: string, b: string): number {
  const [ka, kb] = [chaveDeConfig(a), chaveDeConfig(b)];
  if (ka[0] !== kb[0]) return ka[0] - kb[0];
  if (typeof ka[1] === "string" && typeof kb[1] === "string") return comparaTexto(ka[1], kb[1]);
  if (Array.isArray(ka[1]) && Array.isArray(kb[1])) return comparaPartes(ka[1], kb[1]);
  return 0;
}

/** Sem MCP primeiro, depois as versões do MCP em ordem crescente, e o resto no fim. */
export function ordenarConfigs(configs: Iterable<string>): string[] {
  return [...new Set(configs)].sort(comparaConfigs);
}

function soma(valores: number[]): number {
  // Neumaier: a média do relatório vem de uma soma exata.
  let total = 0;
  let compensacao = 0;
  for (const v of valores) {
    const t = total + v;
    compensacao += Math.abs(total) >= Math.abs(v) ? total - t + v : v - t + total;
    total = t;
  }
  return total + compensacao;
}

/** `toFixed` com empate exato para o par, como o `format` do Python. */
function fixo(x: number, casas: 0 | 2): string {
  const escala = casas === 0 ? 2 : 8;
  const empate = Number.isInteger(x * escala) && (x * escala) % 2 !== 0;
  if (!empate) return x.toFixed(casas);
  const baixo = Math.floor(x * 10 ** casas);
  return ((baixo % 2 === 0 ? baixo : baixo + 1) / 10 ** casas).toFixed(casas);
}

function valorNumerico(r: Registro, metrica: keyof Metricas): number | null {
  const bruto = r.metricas[metrica];
  return bruto === null || bruto === undefined ? null : Number(bruto);
}

export function mediaDe(registros: Registro[], metrica: keyof Metricas): string {
  const valores = registros
    .map((r) => valorNumerico(r, metrica))
    .filter((v): v is number => v !== null);
  if (valores.length === 0) return SEM_DADO;
  const m = soma(valores) / valores.length;
  return m >= 100 ? fixo(m, 0) : fixo(m, 2);
}

export interface LinhaResumo {
  config: string;
  n: number;
  valores: string[];
}

export interface LinhaCenario {
  caso: string;
  celulas: string[];
}

export interface AvaliacaoDoAgente {
  agente: string;
  configs: string[];
  resumo: LinhaResumo[];
  cenarios: LinhaCenario[];
}

/** Médias do conjunto usuário por agente, com as configurações lado a lado. */
export function avaliacaoAmpla(registros: Registro[]): AvaliacaoDoAgente[] {
  const rs = registros.filter(
    (r) => r.conjunto === "usuario" && (r.estado === "passou" || r.estado === "falhou"),
  );
  if (rs.length === 0) return [];
  const configs = ordenarConfigs(rs.map((r) => r.config));
  const agentes = [...new Set(rs.map((r) => r.agente))].sort(comparaTexto);
  return agentes.map((agente) => {
    const doAgente = rs.filter((r) => r.agente === agente);
    const resumo = configs.flatMap((config) => {
      const grupo = doAgente.filter((r) => r.config === config);
      return grupo.length === 0
        ? []
        : [{ config, n: grupo.length, valores: METRICAS_AMPLAS.map(([k]) => mediaDe(grupo, k)) }];
    });
    const casos = [...new Set(doAgente.map((r) => r.caso))].sort(comparaTexto);
    const cenarios = casos.map((caso) => ({
      caso,
      celulas: configs.map((config) => {
        const grupo = doAgente.filter((r) => r.caso === caso && r.config === config);
        return grupo.length === 0 ? SEM_DADO : POR_CENARIO.map((k) => mediaDe(grupo, k)).join(" / ");
      }),
    }));
    return { agente, configs, resumo, cenarios };
  });
}
