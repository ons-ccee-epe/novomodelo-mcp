import { loteDeTools, type Decisao, type Manifesto, type Metricas, type Registro, type Rodada } from "./rodada";

export const SHA_A = "a".repeat(64);
export const SHA_B = "b".repeat(64);

export const METRICAS_VAZIAS: Metricas = {
  acerto_tool: null,
  contornos: null,
  aprovacoes: null,
  rigidez: null,
  erros_envelope: null,
  t_primeira_tool: null,
  t_total: null,
  tokens_entrada: null,
  tokens_saida: null,
  resposta_correta: null,
  interrupcoes: null,
  t_primeira_interrupcao: null,
  maior_trecho_sem_interrupcao: null,
  indice_autonomia: null,
  comandos_terminal: null,
  nota_juiz: null,
};

export function registro(parcial: Partial<Omit<Registro, "metricas">> & { metricas?: Partial<Metricas> } = {}): Registro {
  const { metricas, ...resto } = parcial;
  return {
    schema_versao: 1,
    rodada: "r1",
    conjunto: "usuario",
    caso: "caso-a",
    agente: "claude",
    config: "mcp-1.0",
    repeticao: 0,
    estado: "passou",
    motivo: "",
    tools: [],
    duracao_s: 10,
    ...resto,
    metricas: { ...METRICAS_VAZIAS, ...metricas },
  };
}

export function manifesto(parcial: Partial<Manifesto> = {}): Manifesto {
  return {
    schema_versao: 1,
    rodada: "r1",
    criado_em: "2026-01-02T03:04:05Z",
    configs: ["sem-mcp", "mcp-1.0", "mcp-1.1"],
    conjuntos: ["usuario"],
    agentes: ["claude", "kiro"],
    repeticoes: 3,
    flags: { completa: true },
    versoes: {
      novomodelo: "9.0.0",
      "novomodelo-bridge": "9.1.0",
      "claude-code": "3.0.0",
      "kiro-cli": "4.0.0",
      "juiz-modelo": "juiz-x",
      "juiz-temperatura": "0",
      "mcp:mcp-1.0": "1.0.0",
      "mcp:mcp-1.1": "1.1.0",
    },
    commit_bateria: "abc1234",
    wheels: {
      "mcp-1.0": { arquivo: "pacote-1.0.0.whl", sha256: SHA_A, origem: "registro-publico" },
      "mcp-1.1": { arquivo: "pacote-1.1.0.whl", sha256: SHA_B, origem: "build-local" },
    },
    imagens: { "bateria-claude:1": { "claude-code": "3.0.0", novomodelo: "9.0.0" } },
    filtro: null,
    ...parcial,
  };
}

export const DECISAO_GO: Decisao = {
  schema_versao: 1,
  alvo: "mcp-1.1",
  base: "mcp-1.0 · rodada r0",
  veredito: "go",
  bloqueios: [],
  inconclusivos: [],
  pulados: [],
  sem_base: [],
  ausentes: [],
  incompleto: [],
};

export function rodada(id: string, registros: Registro[], parcial: Partial<Rodada> = {}): Rodada {
  const m = manifesto({ rodada: id });
  return {
    rodada: id,
    bloqueada: false,
    em_andamento: false,
    disparo: null,
    erro: null,
    criado_em: m.criado_em,
    configs: [...m.configs],
    conjuntos: [...m.conjuntos],
    agentes: [...m.agentes],
    repeticoes: m.repeticoes,
    filtro: null,
    commit_bateria: m.commit_bateria,
    manifesto: m,
    registros,
    go_no_go: DECISAO_GO,
    ...parcial,
  };
}

/** Corpo cru de `GET /api/rodadas/{id}`, como o launcher devolve. */
export function corpoDetalhe(id: string, registros: Registro[]): Record<string, unknown> {
  const r = rodada(id, registros);
  return { ...r, erro: undefined };
}

export interface LinhaDeTools {
  caso: string;
  estado?: Registro["estado"];
  duracao_s?: number;
  tools?: Array<[nome: string, duracao_s: number | null]>;
  repeticao?: number;
  motivo?: string;
}

/** Registros do conjunto tools (config mcp-1.0, agente claude) a partir de linhas curtas. */
export function registrosDeTools(linhas: LinhaDeTools[]): Registro[] {
  return linhas.map((l) =>
    registro({
      conjunto: "tools",
      caso: l.caso,
      estado: l.estado ?? "passou",
      duracao_s: l.duracao_s ?? 1,
      repeticao: l.repeticao ?? 0,
      motivo: l.motivo ?? "",
      tools: (l.tools ?? []).map(([nome, duracao_s]) => ({ nome, ok: true, duracao_s })),
    }),
  );
}

/** O lote do conjunto tools de uma rodada sintética, como as telas de gráficos o leem. */
export function loteSintetico(
  id: string,
  criado_em: string,
  linhas: LinhaDeTools[],
  config = "mcp-1.0",
) {
  const r = rodada(id, registrosDeTools(linhas).map((x) => ({ ...x, rodada: id, config })), {
    criado_em,
  });
  return loteDeTools(r, config, "claude");
}

/** Caminhos de máquina montados em tempo de execução, para os testes de limpeza. */
export const CAMINHO_POSIX = ["", "home", "pessoa"].join("/");
export const CAMINHO_WINDOWS = ["C:", "Users", "pessoa"].join("\\");
