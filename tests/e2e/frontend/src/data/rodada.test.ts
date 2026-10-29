import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CAMPOS_BLOQUEIO,
  CAMPOS_DECISAO,
  OPCIONAIS_DECISAO,
  CAMPOS_MANIFESTO,
  CAMPOS_METRICAS,
  CAMPOS_REGISTRO,
  CONJUNTOS,
  ESTADOS,
  REGRAS,
  VEREDITOS,
  VersaoDesconhecida,
  adaptarDecisao,
  avaliacaoAmpla,
  carregarRodada,
  carregarRodadas,
  comparar,
  dispararRodada,
  justificativaDoJuiz,
  limparCaminhos,
  loteDeTools,
  ordenarConfigs,
  porVersao,
} from "./rodada";
import {
  CAMINHO_POSIX,
  CAMINHO_WINDOWS,
  DECISAO_GO,
  corpoDetalhe,
  manifesto,
  registro,
  registrosDeTools,
  rodada,
} from "./fixtures.testutil";

const SCHEMAS = resolve(dirname(fileURLToPath(import.meta.url)), "../../../resultado/schemas");

function schema(nome: string): {
  required: string[];
  properties: Record<string, { enum?: string[] }> & {
    metricas?: { required: string[]; properties: Record<string, unknown> };
  };
} {
  return JSON.parse(readFileSync(resolve(SCHEMAS, `${nome}.schema.json`), "utf-8"));
}

function respostas(corpo: unknown, ok = true, status = 200) {
  const fetchMock = vi.fn(
    async () => ({ ok, status, json: async () => corpo }) as unknown as Response,
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("tipos conferidos contra os schemas", () => {
  it("os campos do manifesto, do registro e das métricas são os dos schemas", () => {
    const m = schema("manifesto");
    const r = schema("registro");
    expect(Object.keys(CAMPOS_MANIFESTO).sort()).toEqual(Object.keys(m.properties).sort());
    expect(Object.keys(CAMPOS_MANIFESTO).sort()).toEqual([...m.required].sort());
    expect(Object.keys(CAMPOS_REGISTRO).sort()).toEqual(Object.keys(r.properties).sort());
    expect(Object.keys(CAMPOS_REGISTRO).sort()).toEqual([...r.required].sort());
    const metricas = r.properties.metricas!;
    expect(Object.keys(CAMPOS_METRICAS).sort()).toEqual(Object.keys(metricas.properties).sort());
    expect(Object.keys(CAMPOS_METRICAS).sort()).toEqual([...metricas.required].sort());
  });

  it("os conjuntos e os estados são os dos schemas", () => {
    const r = schema("registro");
    expect([...CONJUNTOS]).toEqual(r.properties.conjunto!.enum);
    expect([...ESTADOS]).toEqual(r.properties.estado!.enum);
  });
});

describe("decisão do go-no-go contra o schema", () => {
  type Esquema = {
    required: string[];
    properties: Record<string, { enum?: string[] }> & {
      bloqueios: {
        items: { required: string[]; properties: Record<string, { enum?: string[] }> };
      };
    };
  };
  const esquema = schema("decisao") as unknown as Esquema;

  it("os campos e os enums são os do schema", () => {
    expect(Object.keys(CAMPOS_DECISAO).sort()).toEqual(Object.keys(esquema.properties).sort());
    const opcionais = Object.keys(OPCIONAIS_DECISAO);
    expect(
      Object.keys(CAMPOS_DECISAO)
        .filter((c) => !opcionais.includes(c))
        .sort(),
    ).toEqual([...esquema.required].sort());
    expect(opcionais.every((c) => !esquema.required.includes(c))).toBe(true);
    const bloqueio = esquema.properties.bloqueios.items;
    expect(Object.keys(CAMPOS_BLOQUEIO).sort()).toEqual([...bloqueio.required].sort());
    expect([...VEREDITOS]).toEqual(esquema.properties.veredito!.enum);
    expect([...REGRAS]).toEqual(bloqueio.properties.regra!.enum);
  });

  it("aceita a decisão válida e recusa versão desconhecida, campo faltando e enum fora", () => {
    expect(adaptarDecisao(DECISAO_GO).veredito).toBe("go");
    expect(() => adaptarDecisao({ ...DECISAO_GO, schema_versao: 2 })).toThrow(VersaoDesconhecida);
    const semBase: Record<string, unknown> = { ...DECISAO_GO };
    delete semBase.base;
    expect(() => adaptarDecisao(semBase)).toThrow(/base/);
    expect(() => adaptarDecisao({ ...DECISAO_GO, veredito: "talvez" })).toThrow(/veredito/);
    const bloqueio = { regra: "outra", conjunto: "tools", caso: "c", agente: "a", evidencia: [] };
    expect(() => adaptarDecisao({ ...DECISAO_GO, bloqueios: [bloqueio] })).toThrow(/regra/);
  });

  it("decisão gravada sem incompleto lê como rodada completa; com incompleto, repassa", () => {
    const semCampo: Record<string, unknown> = { ...DECISAO_GO };
    delete semCampo.incompleto;
    expect(adaptarDecisao(semCampo).incompleto).toEqual([]);
    const falta = ["tools/c/claude/mcp-1.1/3"];
    expect(adaptarDecisao({ ...DECISAO_GO, veredito: "inconclusivo", incompleto: falta }).incompleto).toEqual(falta);
    expect(() => adaptarDecisao({ ...DECISAO_GO, incompleto: "x" })).toThrow(/incompleto/);
  });

  it("carregarRodada recusa uma decisão com schema_versao desconhecido", async () => {
    const corpo = corpoDetalhe("r1", []);
    corpo.go_no_go = { ...DECISAO_GO, schema_versao: 7 };
    respostas(corpo);
    await expect(carregarRodada("r1")).rejects.toBeInstanceOf(VersaoDesconhecida);
  });

  it("repassa o erro que o launcher devolve no lugar da decisão", async () => {
    const corpo = corpoDetalhe("r1", []);
    corpo.go_no_go = { erro: "resultado ilegível" };
    respostas(corpo);
    expect((await carregarRodada("r1")).go_no_go).toEqual({ erro: "resultado ilegível" });
  });
});

describe("limparCaminhos", () => {
  it("troca caminhos POSIX, Windows e UNC, inclusive com espaço no nome", () => {
    expect(limparCaminhos(`falha em ${CAMINHO_POSIX}/Meus Documentos/x.json fim`)).toBe(
      "falha em <caminho> fim",
    );
    expect(limparCaminhos(`abriu ${CAMINHO_WINDOWS}\\Meus Arquivos\\a.txt agora`)).toBe(
      "abriu <caminho> agora",
    );
    expect(limparCaminhos(String.raw`rede \\servidor\pasta\a`)).toBe("rede <caminho>");
    expect(limparCaminhos("'/var/dados com espaço/r1'")).toBe("<caminho>");
    expect(limparCaminhos("mcp/x e tools/caso")).toBe("mcp/x e tools/caso");
  });

  it("tira o prefixo do juiz e limpa a justificativa", () => {
    expect(justificativaDoJuiz("nota 1 abaixo de 2; juiz: ruim em /tmp/a b/c.txt")).toBe("ruim em <caminho>");
    expect(justificativaDoJuiz("falha na execução")).toBe("falha na execução");
  });
});

describe("loteDeTools", () => {
  it("monta o lote a partir dos registros: grupo pela primeira tool, estados e tempos", () => {
    const regs = registrosDeTools([
      { caso: "q1", duracao_s: 2, tools: [["docs_list", 0.5], ["deck_list", 0.25]] },
      { caso: "q2", estado: "falhou", tools: [] },
      { caso: "q3", estado: "erro_infra" },
      { caso: "q4", estado: "pulado" },
    ]);
    const lote = loteDeTools(rodada("r1", regs), "mcp-1.0", "claude");
    expect(lote.batch_id).toBe("r1");
    expect(lote.mcp_version).toBe("1.0.0");
    expect([lote.passed, lote.failed, lote.erro_infra, lote.skipped]).toEqual([1, 1, 1, 1]);
    const [q1] = lote.test_results;
    expect(q1).toMatchObject({ grupo: "docs", latency_ms: 2000, tool_latency_ms: 750, mcp_used: true });
    expect(lote.test_results[1]).toMatchObject({ grupo: "other", tool_latency_ms: null });
    expect(lote.metrics.pct_mcp_used).toBeCloseTo(100 / 3);
    expect(Object.keys(lote.metrics_by_group)).toEqual(["docs", "other"]);
  });

  it("distingue as repetições do mesmo caso", () => {
    const regs = registrosDeTools([
      { caso: "q1", repeticao: 0 },
      { caso: "q1", repeticao: 1 },
    ]);
    const lote = loteDeTools(rodada("r1", regs), "mcp-1.0", "claude");
    expect(lote.test_results.map((r) => r.test_id)).toEqual(["q1#0", "q1#1"]);
  });
});

describe("carregarRodada", () => {
  it("adapta manifesto e registros do schema", async () => {
    const regs = [registro({ metricas: { nota_juiz: 2, acerto_tool: true } })];
    const fetchMock = respostas(corpoDetalhe("r1", regs));
    const r = await carregarRodada("r1");
    expect(fetchMock).toHaveBeenCalledWith("api/rodadas/r1", expect.anything());
    expect(r.rodada).toBe("r1");
    expect(r.manifesto?.wheels["mcp-1.0"]?.sha256).toHaveLength(64);
    expect(r.registros).toHaveLength(1);
    expect(r.registros[0]?.metricas.nota_juiz).toBe(2);
    expect(r.go_no_go).toMatchObject({ veredito: "go", alvo: "mcp-1.1" });
  });

  it("recusa schema_versao desconhecida no manifesto", async () => {
    const corpo = corpoDetalhe("r1", []);
    corpo.manifesto = { ...manifesto(), schema_versao: 2 };
    respostas(corpo);
    await expect(carregarRodada("r1")).rejects.toBeInstanceOf(VersaoDesconhecida);
  });

  it("recusa schema_versao desconhecida num registro", async () => {
    const corpo = corpoDetalhe("r1", [{ ...registro(), schema_versao: 9 }]);
    respostas(corpo);
    await expect(carregarRodada("r1")).rejects.toThrow(/schema_versao 9/);
  });

  it("recusa registro sem campo obrigatório", async () => {
    const quebrado: Record<string, unknown> = { ...registro() };
    delete quebrado.metricas;
    respostas(corpoDetalhe("r1", [quebrado as never]));
    await expect(carregarRodada("r1")).rejects.toThrow(/metricas/);
  });

  it("devolve a rodada ilegível com o erro do launcher, sem registros", async () => {
    respostas({
      rodada: "r1",
      bloqueada: false,
      em_andamento: false,
      disparo: null,
      erro: "resultado ilegível: x",
      registros: [],
    });
    const r = await carregarRodada("r1");
    expect(r.erro).toBe("resultado ilegível: x");
    expect(r.manifesto).toBeNull();
  });

  it("propaga a recusa do launcher", async () => {
    respostas({ detail: "rodada nao encontrada" }, false, 404);
    await expect(carregarRodada("r1")).rejects.toThrow(/rodada nao encontrada/);
  });
});

describe("carregarRodadas", () => {
  it("lê o resumo de cada rodada", async () => {
    const fetchMock = respostas({
      rodadas: [
        { ...rodada("r2", []), manifesto: undefined, registros: undefined, decisoes: undefined },
        { rodada: "r0", bloqueada: false, em_andamento: false, disparo: null, erro: "ilegível" },
      ],
    });
    const lista = await carregarRodadas();
    expect(fetchMock).toHaveBeenCalledWith("api/rodadas", expect.anything());
    expect(lista.map((r) => r.rodada)).toEqual(["r2", "r0"]);
    expect(lista[0]?.configs).toContain("mcp-1.0");
    expect(lista[1]?.erro).toBe("ilegível");
    expect(lista[1]?.configs).toEqual([]);
  });
});

describe("porVersao", () => {
  it("agrupa rodadas por versão do MCP", () => {
    const a = rodada("a", [], { configs: ["sem-mcp", "mcp-1.0"] });
    const b = rodada("b", [], { configs: ["mcp-1.0", "mcp-1.1"] });
    const c = rodada("c", [], { configs: ["sem-mcp"] });
    const grupos = porVersao([a, b, c]);
    expect([...grupos.keys()]).toEqual(["sem-mcp", "mcp-1.0", "mcp-1.1"]);
    expect(grupos.get("mcp-1.0")?.map((r) => r.rodada)).toEqual(["a", "b"]);
    expect(grupos.get("sem-mcp")?.map((r) => r.rodada)).toEqual(["a", "c"]);
  });
});

describe("comparar", () => {
  it("compara duas rodadas e marca regressões", () => {
    const antes = rodada("a", [
      registro({ caso: "caso-a", estado: "passou" }),
      registro({ caso: "caso-b", estado: "falhou" }),
      registro({ caso: "caso-c", estado: "passou" }),
      registro({ caso: "caso-d", estado: "passou" }),
    ]);
    const depois = rodada("b", [
      registro({ caso: "caso-a", estado: "falhou" }),
      registro({ caso: "caso-b", estado: "passou" }),
      registro({ caso: "caso-c", estado: "passou" }),
      registro({ caso: "caso-e", estado: "passou" }),
    ]);
    const difs = comparar(antes, depois);
    const por = Object.fromEntries(difs.map((d) => [d.caso, d]));
    expect(por["caso-a"]).toMatchObject({ tipo: "regressao", antes: "passou", depois: "falhou" });
    expect(por["caso-b"]).toMatchObject({ tipo: "melhora" });
    expect(por["caso-d"]).toMatchObject({ tipo: "regressao", depois: "ausente" });
    expect(por["caso-e"]).toMatchObject({ tipo: "melhora", antes: "ausente" });
    expect(por["caso-c"]).toBeUndefined();
    expect(difs[0]?.tipo).toBe("regressao");
  });

  it("usa a maioria das repetições como estado do caso", () => {
    const antes = rodada("a", [
      registro({ repeticao: 0, estado: "passou" }),
      registro({ repeticao: 1, estado: "passou" }),
      registro({ repeticao: 2, estado: "falhou" }),
    ]);
    const depois = rodada("b", [
      registro({ repeticao: 0, estado: "passou" }),
      registro({ repeticao: 1, estado: "falhou" }),
      registro({ repeticao: 2, estado: "falhou" }),
    ]);
    expect(comparar(antes, depois)).toHaveLength(1);
    expect(comparar(antes, antes)).toEqual([]);
  });
});

describe("avaliacaoAmpla", () => {
  it("ordena as configurações: sem MCP, versões crescentes, o resto", () => {
    expect(ordenarConfigs(["mcp-1.10", "z", "mcp-1.9", "sem-mcp", "mcp-1.9-final"])).toEqual([
      "sem-mcp",
      "mcp-1.9",
      "mcp-1.9-final",
      "mcp-1.10",
      "z",
    ]);
  });

  it("calcula as médias com o arredondamento do relatório e — para ausente", () => {
    const regs = [
      registro({ metricas: { acerto_tool: true, nota_juiz: 2, t_total: 100, tokens_entrada: 1000 } }),
      registro({ repeticao: 1, estado: "falhou", metricas: { acerto_tool: false, nota_juiz: 1, t_total: 101 } }),
      registro({ repeticao: 2, estado: "pulado", metricas: { nota_juiz: 0 } }),
      registro({ conjunto: "tools", metricas: { nota_juiz: 0 } }),
    ];
    const [ampla] = avaliacaoAmpla(regs);
    expect(ampla?.agente).toBe("claude");
    expect(ampla?.resumo).toEqual([
      {
        config: "mcp-1.0",
        n: 2,
        valores: ["0.50", "1.50", "—", "—", "—", "100", "1000"],
      },
    ]);
  });

  it("arredonda empate exato para o par, como o relatório", () => {
    const regs = [
      registro({ metricas: { nota_juiz: 0, contornos: 0 } }),
      registro({ repeticao: 1, metricas: { nota_juiz: 0, contornos: 1 } }),
      registro({ repeticao: 2, metricas: { nota_juiz: 1, contornos: 0 } }),
      registro({ repeticao: 3, metricas: { nota_juiz: 0, contornos: 0 } }),
      registro({ repeticao: 4, metricas: { nota_juiz: 0, contornos: 0 } }),
      registro({ repeticao: 5, metricas: { nota_juiz: 0, contornos: 0 } }),
      registro({ repeticao: 6, metricas: { nota_juiz: 0, contornos: 0 } }),
      registro({ repeticao: 7, metricas: { nota_juiz: 0, contornos: 0 } }),
    ];
    const [ampla] = avaliacaoAmpla(regs);
    // 1/8 = 0.125 -> "0.12" (par), como o formato do relatório.
    expect(ampla?.resumo[0]?.valores.slice(1, 3)).toEqual(["0.12", "0.12"]);
  });

  it("lista os cenários por configuração com o separador do relatório", () => {
    const regs = [
      registro({ config: "sem-mcp", caso: "caso-a", metricas: { acerto_tool: false, nota_juiz: 1, interrupcoes: 4, t_total: 20 } }),
      registro({ config: "mcp-1.0", caso: "caso-a", metricas: { acerto_tool: true, nota_juiz: 2, interrupcoes: 0, t_total: 12.345 } }),
      registro({ config: "mcp-1.0", caso: "caso-b", metricas: { acerto_tool: true } }),
    ];
    const [ampla] = avaliacaoAmpla(regs);
    expect(ampla?.configs).toEqual(["sem-mcp", "mcp-1.0"]);
    expect(ampla?.cenarios).toEqual([
      { caso: "caso-a", celulas: ["0.00 / 1.00 / 4.00 / 20.00", "1.00 / 2.00 / 0.00 / 12.35"] },
      { caso: "caso-b", celulas: ["—", "1.00 / — / — / —"] },
    ]);
  });

  it("não devolve nada sem registros do conjunto usuário", () => {
    expect(avaliacaoAmpla([registro({ conjunto: "tools" })])).toEqual([]);
  });
});

describe("dispararRodada", () => {
  it("envia só os campos da lista branca a POST /api/rodadas, com o header do launcher", async () => {
    const fetchMock = respostas({ rodada: "r9", status: "em_andamento" });
    const estado = await dispararRodada({ mcp: ["sem"], conjuntos: ["usuario"], repeticoes: 3 });
    expect(estado.rodada).toBe("r9");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("api/rodadas");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["X-Launcher"]).toBe("1");
    expect(JSON.parse(init.body as string)).toEqual({
      mcp: ["sem"],
      conjuntos: ["usuario"],
      repeticoes: 3,
    });
  });

  it("mostra o motivo da recusa do launcher", async () => {
    respostas({ detail: "wheel não encontrada" }, false, 422);
    await expect(dispararRodada({ mcp: ["x.whl"] })).rejects.toThrow(/wheel não encontrada/);
  });

  it("não chama as rotas que o launcher não tem mais", async () => {
    const fetchMock = respostas({ rodadas: [] });
    await carregarRodadas();
    const urls = fetchMock.mock.calls.map((c) => String((c as unknown[])[0]));
    expect(urls.some((u) => /providers|\/runs/.test(u))).toBe(false);
  });
});
