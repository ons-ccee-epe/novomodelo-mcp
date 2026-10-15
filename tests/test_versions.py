"""Versões das peças, aviso em toda resposta e verificação de versão nova (sem rede real)."""
import json
import re
import ssl
import sys
import time
import types
import urllib.error
from pathlib import Path

import pytest

from novomodelo_mcp.adapters import versions as V
from novomodelo_mcp.server import build_server

TUDO_018 = {"executavel": "0.18.0", "biblioteca": "0.18.0", "bridge": "0.18.0"}


@pytest.fixture(autouse=True)
def _limpa_caches():
    V.reset_caches()
    yield
    V.reset_caches()


@pytest.fixture
def pecas(monkeypatch):
    """Substitui a leitura das peças locais; devolve o dict para o teste ajustar."""
    estado = dict(TUDO_018)
    chamadas = {"n": 0}

    def _ler(settings):
        chamadas["n"] += 1
        return {k: ({"versao": v} if v else {"versao": None, "motivo": "não encontrado"})
                for k, v in estado.items()} | {"docs": {"versao": None, "motivo": "sem manifesto"}}

    monkeypatch.setattr(V, "_read_local", _ler)
    monkeypatch.setattr(V, "expected_version", lambda: "0.18.0")
    return estado, chamadas


@pytest.fixture
def sem_rede(monkeypatch):
    """Qualquer tentativa de abrir conexão falha o teste."""
    abertas = []

    def _proibido(*a, **k):
        abertas.append(a)
        raise AssertionError("rede usada fora do server_info")

    monkeypatch.setattr(V, "_open", _proibido)
    return abertas


# ── normalização e versão esperada ────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado", [("v0.18.0", "0.18.0"), ("0.18.0.post2", "0.18.0"),
                                            (" 0.18.0 ", "0.18.0"), ("", None), (None, None)])
def test_normalize_version(texto, esperado):
    assert V.normalize_version(texto) == esperado


def test_mcp_em_post_casa_com_as_pecas(pecas):
    estado, _ = pecas
    estado["bridge"] = "0.18.0.post2"
    assert V.version_warnings(object()) == []


# ── avisos locais ─────────────────────────────────────────────────────────────

def test_tudo_na_mesma_versao_sem_aviso(pecas):
    assert V.version_warnings(object()) == []


def test_bridge_de_outra_versao_avisa_com_o_comando(pecas):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    avisos = V.version_warnings(object())
    assert len(avisos) == 1 and "0.17.0" in avisos[0] and "0.18.0" in avisos[0]
    assert "novomodelo-bridge==0.18.0" in avisos[0]


def test_peca_ausente_tem_aviso_proprio(pecas):
    estado, _ = pecas
    estado["executavel"] = None
    avisos = V.version_warnings(object())
    assert len(avisos) == 1 and "não encontrado" in avisos[0]
    assert "versão" not in avisos[0].split(":")[0]
    assert "novomodelo-cli-installer" in avisos[0]


PECA_AO_AGENTE = "Peça ao agente: “instale o executável do novomodelo” (tool instalar_novomodelo)"


def _primeiro_o_agente_depois_o_manual(aviso):
    agente, manual = aviso.index(PECA_AO_AGENTE), aviso.index("Manual: ")
    assert agente < manual
    assert "novomodelo-cli-installer" in aviso[manual:]
    assert "novomodelo-cli-installer" not in aviso[:manual]


def test_executavel_ausente_sugere_primeiro_pedir_ao_agente(pecas):
    estado, _ = pecas
    estado["executavel"] = None
    [aviso] = V.version_warnings(object())
    _primeiro_o_agente_depois_o_manual(aviso)


def test_executavel_em_outra_versao_sugere_primeiro_pedir_ao_agente(pecas):
    estado, _ = pecas
    estado["executavel"] = "0.17.0"
    [aviso] = V.version_warnings(object())
    _primeiro_o_agente_depois_o_manual(aviso)


def test_instrucoes_do_servidor_usam_a_mesma_frase():
    from novomodelo_mcp.server import SERVER_INSTRUCTIONS
    assert "“instale o executável do novomodelo”" in SERVER_INSTRUCTIONS
    assert "`instalar_novomodelo`" in SERVER_INSTRUCTIONS


def _bridge_do_pacote(monkeypatch):
    ler = V._read_local
    monkeypatch.setattr(V, "_read_local", lambda s: ler(s) | {
        "bridge": {"versao": ler(s)["bridge"]["versao"], "origem": "pacote"}})


def _guia():
    return V.GUIDE_URL


def test_executavel_mais_novo_que_o_mcp_pode_usar_e_confere_a_pagina(pecas, monkeypatch):
    estado, _ = pecas
    estado["executavel"] = "0.18.1"
    _bridge_do_pacote(monkeypatch)
    [aviso] = V.version_warnings(object())
    assert aviso.startswith(
        "O executável novomodelo está na 0.18.1 e o MCP na 0.18.0. Pode usar. Confira na página "
        f"do guia ({_guia()}) se já saiu o MCP 0.18.1 e, quando sair, atualize as peças juntas.")
    assert ("A validação da v1 é na 0.18.0. Se você atualizar o executável novomodelo, avise no "
            "card: os resultados deixam de ser comparáveis com os dos outros validadores.") in aviso
    assert "novomodelo-cli-installer" not in aviso and "novomodelo_mcp-0.18.1" not in aviso


def test_endereco_do_guia_e_o_da_pagina():
    import importlib.util
    raiz = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("gerar_guia", raiz / "scripts" / "gerar_guia.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    pagina = (raiz / "guia" / "index.html").read_text(encoding="utf-8")
    assert V.GUIDE_URL == g.current(pagina, "espelho") + "/index.html"


def test_executavel_mais_velho_manda_instalar_a_versao_do_mcp(pecas):
    estado, _ = pecas
    estado["executavel"] = "0.17.0"
    [aviso] = V.version_warnings(object())
    assert "v0.18.0/novomodelo-cli-installer" in aviso and "instalar_novomodelo" in aviso


def test_bridge_instalado_a_parte_e_mais_novo_pode_usar(pecas):
    estado, _ = pecas
    estado["bridge"] = "0.18.1"
    [aviso] = V.version_warnings(object())
    assert aviso.startswith("O novomodelo-bridge está na 0.18.1 e o MCP na 0.18.0. Pode usar.")
    assert "==0.18.0" not in aviso


_REBAIXAR = re.compile(r"volte|voltar|rebaix|downgrade|mantenha", re.I)


def test_bridge_do_pacote_atras_tem_o_comando_do_mcp(pecas, monkeypatch):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    _bridge_do_pacote(monkeypatch)
    [aviso] = V.version_warnings(object())
    assert "uv tool install --force" in aviso and "novomodelo_mcp-0.18.0" in aviso


@pytest.mark.parametrize("executavel", ["0.17.0", "0.18.0", "0.18.1", None])
@pytest.mark.parametrize("bridge", ["0.17.0", "0.18.0", "0.18.1"])
def test_nenhum_aviso_manda_rebaixar_nem_instalar_um_mcp_novo(pecas, executavel, bridge):
    estado, _ = pecas
    estado.update(executavel=executavel, bridge=bridge)
    texto = " ".join(V.version_warnings(object()))
    assert not _REBAIXAR.search(texto), texto
    for velha in ("0.17.0",):
        assert f"v{velha}/novomodelo-cli-installer" not in texto and f"=={velha}" not in texto
    assert "novomodelo_mcp-0.18.1" not in texto and "/releases/tag/v0.18.1" not in texto


def test_leitura_das_pecas_uma_vez_por_processo(pecas):
    _, chamadas = pecas
    settings = object()
    for _ in range(5):
        V.version_warnings(settings)
    assert chamadas["n"] == 1


def test_sem_versao_esperada_nao_avisa(pecas, monkeypatch):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    monkeypatch.setattr(V, "expected_version", lambda: None)
    assert V.version_warnings(object()) == []


# ── aviso em toda tool ────────────────────────────────────────────────────────

def test_toda_tool_registrada_passa_pelo_aviso():
    tools = build_server()._tool_manager.list_tools()
    sem = sorted(t.name for t in tools if not getattr(t.fn, "_avisos_de_versao", False))
    assert sem == []


@pytest.mark.parametrize("tool,args", [("run_status", {"job_id": "nao-existe"}),
                                       ("schema_list", {}),
                                       ("results_list_entities", {"output_dir": "/nao/existe"})])
def test_bridge_017_aparece_em_tools_sem_cap_envelope(pecas, sem_rede, monkeypatch, tool, args):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    fn = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}[tool]
    env = fn(**args)
    assert any("novomodelo-bridge==0.18.0" in a for a in env["avisos_de_versao"])
    assert sem_rede == []


def test_com_tudo_018_o_campo_nao_aparece(pecas, sem_rede):
    fn = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}["schema_list"]
    assert "avisos_de_versao" not in fn()


def test_embrulho_preserva_o_schema_publicado():
    tools = {t.name: t for t in build_server()._tool_manager.list_tools()}
    fmt = tools["bridge_compare_newave"].parameters["properties"]["fmt"]
    assert fmt["enum"] == ["console", "html", "csv", "parquet", "json", "all"]


def test_aviso_que_quebra_nao_derruba_a_tool(monkeypatch):
    monkeypatch.setattr(V, "_read_local", lambda settings: 1 / 0)
    fn = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}["schema_list"]
    assert fn()["status"] == "ok"


# ── rede: domínios, contexto TLS, falhas ──────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://github.com/ons-ccee-epe/novomodelo/releases/download/v0.18.0/x",
    "https://api.github.com/repos/ons-ccee-epe/novomodelo/releases/latest",
    "https://pypi.org/pypi/novomodelo-bridge/json",
])
def test_dominios_permitidos(url):
    assert V.allowed_url(url)


@pytest.mark.parametrize("url", [
    "http://github.com/ons-ccee-epe/novomodelo",
    "https://github.com/outra-org/novomodelo",
    "https://api.github.com/repos/<repositório anterior>/releases/latest",
    "https://pypi.org/pypi/outro-pacote/json",
    "https://release-assets.githubusercontent.com/x",
    "https://evil.example/ons-ccee-epe/",
])
def test_dominios_recusados(url):
    assert not V.allowed_url(url)


def test_redirecionamento_so_para_o_cdn_do_github():
    assert V.allowed_url("https://release-assets.githubusercontent.com/x", redirect=True)
    assert not V.allowed_url("https://evil.example/x", redirect=True)


def test_url_fora_da_lista_e_recusada_sem_abrir_conexao(sem_rede):
    r = V.fetch_json("https://evil.example/x.json", timeout=1)
    assert r["aviso_rede"] and "não permitido" in r["aviso_rede"] and sem_rede == []


def test_contexto_do_truststore_quando_disponivel(monkeypatch):
    usado = {}

    class _Ctx:
        def __init__(self, proto):
            usado["proto"] = proto

    monkeypatch.setitem(sys.modules, "truststore", types.SimpleNamespace(SSLContext=_Ctx))
    ctx = V._ssl_context()
    assert isinstance(ctx, _Ctx) and usado["proto"] == ssl.PROTOCOL_TLS_CLIENT


def test_sem_truststore_cai_no_contexto_padrao(monkeypatch):
    monkeypatch.setitem(sys.modules, "truststore", None)
    assert isinstance(V._ssl_context(), ssl.SSLContext)


def test_truststore_nao_e_injetado_no_processo():
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(V))
    nomes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "inject_into_ssl" not in nomes


def test_falha_de_certificado_vira_aviso_rede(monkeypatch):
    def _cert(req, *, timeout, context):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("self-signed certificate"))
    monkeypatch.setattr(V, "_open", _cert)
    r = V.fetch_json("https://pypi.org/pypi/novomodelo-bridge/json", timeout=1)
    assert "certificado" in r["aviso_rede"]


# ── versão nova no server_info ────────────────────────────────────────────────

def _respostas(monkeypatch, tag="v0.19.0", bridge="0.19.0", atraso=0.0):
    def _abrir(req, *, timeout, context):
        time.sleep(atraso)
        url = req.full_url
        corpo = {"tag_name": tag} if "api.github.com" in url else {"info": {"version": bridge}}
        return json.dumps(corpo).encode()
    monkeypatch.setattr(V, "_open", _abrir)


def test_release_mais_novo_nao_da_o_mcp_novo_como_existente(pecas, monkeypatch):
    _respostas(monkeypatch)
    mcp = V.update_check(object())["mcp"]
    assert mcp["status"] == "a_conferir" and "link" not in mcp and "comando" not in mcp
    assert f"Confira na página do guia ({_guia()}) se já saiu o MCP 0.19.0" in mcp["nota"]


def test_release_mais_novo_nao_manda_instalar_so_o_executavel(pecas, monkeypatch):
    _respostas(monkeypatch)
    nova = V.update_check(object())
    assert nova["novomodelo"]["status"] == "nova" and nova["novomodelo"]["mais_recente"] == "0.19.0"
    assert "comando" not in nova["novomodelo"]
    assert "o MCP está na 0.18.0" in nova["novomodelo"]["nota"]
    assert "comando" not in nova["bridge"] and nova["bridge"]["mais_recente"] == "0.19.0"
    assert not any(_REBAIXAR.search(p.get("nota", "")) for p in nova.values())


def test_versao_atual_nao_sugere_atualizar(pecas, monkeypatch):
    _respostas(monkeypatch, tag="v0.18.0", bridge="0.18.0")
    nova = V.update_check(object())
    assert nova["novomodelo"]["status"] == "atual" and "comando" not in nova["novomodelo"]


def test_sem_rede_nao_foi_possivel_verificar_em_menos_de_3s(pecas, monkeypatch):
    def _cai(req, *, timeout, context):
        raise urllib.error.URLError("sem rede")
    monkeypatch.setattr(V, "_open", _cai)
    t0 = time.perf_counter()
    nova = V.update_check(object())
    assert time.perf_counter() - t0 < 3
    assert nova["novomodelo"]["status"] == "nao_foi_possivel_verificar"
    assert nova["novomodelo"]["aviso_rede"]


def test_rede_lenta_respeita_o_orcamento(pecas, monkeypatch):
    _respostas(monkeypatch, atraso=5)
    t0 = time.perf_counter()
    nova = V.update_check(object(), budget_s=0.5)
    assert time.perf_counter() - t0 < 2
    assert nova["bridge"]["status"] == "nao_foi_possivel_verificar"


def test_verificacao_de_versao_nova_vale_por_6_horas(pecas, monkeypatch):
    chamadas, agora = [], [1000.0]
    _respostas(monkeypatch)
    abrir = V._open
    monkeypatch.setattr(V, "_open", lambda req, **k: chamadas.append(req) or abrir(req, **k))
    monkeypatch.setattr(V.time, "monotonic", lambda: agora[0])
    V.update_check(object())
    agora[0] += 6 * 3600 - 1
    V.update_check(object())
    assert len(chamadas) == 2   # novomodelo + bridge, uma vez só nas 6 h
    agora[0] += 2
    V.update_check(object())
    assert len(chamadas) == 4   # passadas as 6 h, consulta de novo


def test_docs_de_outra_versao_avisam_e_sem_manifesto_nao(pecas, monkeypatch):
    estado, _ = pecas
    ler = V._read_local
    monkeypatch.setattr(V, "_read_local", lambda s: ler(s) | {"docs": {"versao": "0.17.0"}})
    assert any("docs embutidas na versão 0.17.0" in a for a in V.version_warnings(object()))
    V.reset_caches()
    monkeypatch.setattr(V, "_read_local", ler)
    assert V.version_warnings(object()) == []


def test_docs_embutidas_reais_tem_a_versao_do_manifesto():
    piece = V._docs_piece()
    assert piece["versao"] and piece["commit"]
