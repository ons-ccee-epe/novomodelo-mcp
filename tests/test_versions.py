"""Versões das peças, aviso em toda resposta e verificação de versão nova (sem rede real)."""
import json
import ssl
import sys
import time
import types
import urllib.error

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


def _bridge_do_pacote(monkeypatch):
    ler = V._read_local
    monkeypatch.setattr(V, "_read_local", lambda s: ler(s) | {
        "bridge": {"versao": ler(s)["bridge"]["versao"], "origem": "pacote"}})


def test_executavel_mais_novo_manda_atualizar_o_mcp_e_nunca_rebaixar(pecas, monkeypatch):
    estado, _ = pecas
    estado["executavel"] = "0.18.1"
    _bridge_do_pacote(monkeypatch)
    avisos = V.version_warnings(object())
    assert len(avisos) == 1, avisos
    assert "atualize o MCP para 0.18.1" in avisos[0]
    assert "uv tool install --force" in avisos[0] and "novomodelo_mcp-0.18.1" in avisos[0]
    assert "/releases/tag/v0.18.1" in avisos[0]
    assert "v0.18.0/novomodelo-cli-installer" not in avisos[0]


def test_mcp_atras_diz_que_o_bridge_e_a_biblioteca_vem_junto(pecas):
    estado, _ = pecas
    estado["executavel"] = "0.18.1"
    assert "vêm junto" in V.version_warnings(object())[0]


def test_executavel_mais_velho_manda_instalar_a_versao_do_mcp(pecas):
    estado, _ = pecas
    estado["executavel"] = "0.17.0"
    [aviso] = V.version_warnings(object())
    assert "v0.18.0/novomodelo-cli-installer" in aviso and "instalar_novomodelo" in aviso


def test_bridge_instalado_a_parte_e_atrasado_ganha_linha_propria(pecas):
    estado, _ = pecas
    estado["executavel"] = "0.18.1"
    avisos = V.version_warnings(object())
    assert len(avisos) == 2 and "novomodelo-bridge==0.18.1" in avisos[1]


def test_bridge_do_pacote_atras_tem_o_comando_do_mcp(pecas, monkeypatch):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    _bridge_do_pacote(monkeypatch)
    [aviso] = V.version_warnings(object())
    assert "uv tool install --force" in aviso and "novomodelo_mcp-0.18.0" in aviso


@pytest.mark.parametrize("executavel", ["0.17.0", "0.18.0", "0.18.1", None])
@pytest.mark.parametrize("bridge", ["0.17.0", "0.18.0", "0.18.1"])
def test_nenhum_aviso_aponta_para_versao_abaixo_da_mais_nova(pecas, executavel, bridge):
    estado, _ = pecas
    estado.update(executavel=executavel, bridge=bridge)
    alvo = max(v for v in ("0.18.0", executavel, bridge) if v)
    texto = " ".join(V.version_warnings(object()))
    for velha in ("0.17.0", "0.18.0", "0.18.1"):
        if velha < alvo:
            assert f"v{velha}/novomodelo-cli-installer" not in texto
            assert f"=={velha}" not in texto and f"novomodelo_mcp-{velha}" not in texto


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


def test_release_mais_novo_mostra_o_comando_e_o_link_do_mcp(pecas, monkeypatch):
    _respostas(monkeypatch)
    nova = V.update_check(object())
    assert nova["novomodelo"]["mais_recente"] == "0.19.0" and nova["novomodelo"]["comando"]
    assert nova["bridge"]["mais_recente"] == "0.19.0"
    assert nova["mcp"]["link"].endswith("/releases/tag/v0.19.0")


def test_release_mais_novo_traz_o_comando_do_mcp(pecas, monkeypatch):
    _respostas(monkeypatch)
    mcp = V.update_check(object())["mcp"]
    assert "uv tool install --force" in mcp["comando"] and "novomodelo_mcp-0.19.0" in mcp["comando"]


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


def test_verificacao_de_versao_nova_uma_vez_por_processo(pecas, monkeypatch):
    chamadas = []
    _respostas(monkeypatch)
    abrir = V._open
    monkeypatch.setattr(V, "_open", lambda req, **k: chamadas.append(req) or abrir(req, **k))
    V.update_check(object())
    V.update_check(object())
    assert len(chamadas) == 2   # novomodelo + bridge, uma vez só


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
