"""Versões das peças, aviso em toda resposta e verificação de versão nova (sem rede real)."""

import json
import re
import ssl
import sys
import time
import types
import urllib.error

import pytest

from novomodelo_mcp.adapters import versions as V
from novomodelo_mcp.server import build_server

TUDO_018 = {"executable": "0.18.0", "library": "0.18.0", "bridge": "0.18.0"}


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
        return {
            k: ({"version": v} if v else {"version": None, "reason": "não encontrado"})
            for k, v in estado.items()
        } | {"docs": {"version": None, "reason": "sem manifesto"}}

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


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("v0.18.0", "0.18.0"),
        ("0.18.0.post2", "0.18.0"),
        (" 0.18.0 ", "0.18.0"),
        ("", None),
        (None, None),
    ],
)
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
    estado["executable"] = None
    avisos = V.version_warnings(object())
    assert len(avisos) == 1 and "não encontrado" in avisos[0]
    assert "versão" not in avisos[0].split(":")[0]
    assert "novomodelo-cli-installer" in avisos[0]


PECA_AO_AGENTE = "Peça ao agente: “instale o executável do novomodelo” (tool install_novomodelo)"


def _primeiro_o_agente_depois_o_manual(aviso):
    agente, manual = aviso.index(PECA_AO_AGENTE), aviso.index("Manual: ")
    assert agente < manual
    assert "novomodelo-cli-installer" in aviso[manual:]
    assert "novomodelo-cli-installer" not in aviso[:manual]


def test_executavel_ausente_sugere_primeiro_pedir_ao_agente(pecas):
    estado, _ = pecas
    estado["executable"] = None
    [aviso] = V.version_warnings(object())
    _primeiro_o_agente_depois_o_manual(aviso)


def test_executavel_em_outra_versao_sugere_primeiro_pedir_ao_agente(pecas):
    estado, _ = pecas
    estado["executable"] = "0.17.0"
    [aviso] = V.version_warnings(object())
    _primeiro_o_agente_depois_o_manual(aviso)


def test_instrucoes_do_servidor_usam_a_mesma_frase():
    from novomodelo_mcp.server import SERVER_INSTRUCTIONS

    assert "“instale o executável do novomodelo”" in SERVER_INSTRUCTIONS
    assert "`install_novomodelo`" in SERVER_INSTRUCTIONS


def _bridge_do_pacote(monkeypatch):
    ler = V._read_local
    monkeypatch.setattr(
        V,
        "_read_local",
        lambda s: ler(s) | {"bridge": {"version": ler(s)["bridge"]["version"], "origin": "pacote"}},
    )


def test_executavel_0_19_com_mcp_0_18(pecas, monkeypatch):
    estado, _ = pecas
    estado["executable"] = "0.19.0"
    _bridge_do_pacote(monkeypatch)
    [aviso] = V.version_warnings(object())
    assert aviso.startswith("O executável novomodelo está na 0.19.0 e o MCP na 0.18.0;")
    assert V.mcp_install_command("0.19.0") in aviso
    assert "v0.18.0/novomodelo-cli-installer" in aviso and "install_novomodelo" in aviso
    assert aviso.index(V.mcp_install_command("0.19.0")) < aviso.index("novomodelo-cli-installer")


def test_so_a_biblioteca_diverge(pecas):
    estado, _ = pecas
    estado["library"] = "0.17.0"
    [aviso] = V.version_warnings(object())
    assert "biblioteca novomodelo-python" in aviso
    assert V.mcp_install_command("0.18.0") in aviso


@pytest.mark.parametrize("peca,esperada", [("0.18.1", "0.18.0"), ("0.18.0", "0.18.1")])
def test_patch_diferente_avisa_nos_dois_sentidos(pecas, monkeypatch, peca, esperada):
    estado, _ = pecas
    estado.update(executable=esperada, library=esperada, bridge=peca)
    monkeypatch.setattr(V, "expected_version", lambda: esperada)
    [aviso] = V.version_warnings(object())
    assert peca in aviso and esperada in aviso


def test_desalinhado_nao_bloqueia(pecas, sem_rede, monkeypatch):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    fns = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}
    docs = fns["docs_list"]()
    run = fns["run_status"](job_id="nao-existe")
    assert docs["version_warnings"] and run["version_warnings"]
    assert docs["status"] == "ok" and docs["count"] > 0 and docs["pages"]
    assert run["status"] == "error"


def test_versao_ilegivel_sem_aviso_e_sem_excecao(pecas):
    estado, _ = pecas
    estado["bridge"] = "dev"
    assert V.version_warnings(object()) == []


def test_instrucoes_mandam_oferecer_os_comandos():
    from novomodelo_mcp.server import SERVER_INSTRUCTIONS

    assert "`version_warnings`" in SERVER_INSTRUCTIONS
    assert "ofereça rodar os comandos" in SERVER_INSTRUCTIONS
    assert "o MCP continua funcionando" in SERVER_INSTRUCTIONS


def test_aviso_nao_usa_a_rede(pecas, monkeypatch):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    monkeypatch.setattr(V, "fetch_bytes", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(V, "fetch_json", lambda *a, **k: 1 / 0)
    assert len(V.version_warnings(object())) == 1


#: As mensagens só apontam para os canais públicos: o produto é das três instituições.
_PUBLICO = (
    "https://github.com/ons-ccee-epe/",
    "https://pypi.org/",
    "https://docs.modelossetoreletrico.org.br/",
)


@pytest.mark.parametrize("executavel", ["0.17.0", "0.18.1", "0.19.0", None])
def test_produto_sem_referencia_interna(pecas, monkeypatch, executavel):
    estado, _ = pecas
    estado.update(executable=executavel, bridge="0.18.1")
    _respostas(monkeypatch)
    nova = V.update_check(object())
    texto = " ".join(V.version_warnings(object())) + " ".join(
        p.get("note", "") for p in nova.values()
    )
    urls = re.findall(r"https?://[^\s`'\")]+", texto)
    assert urls and all(u.startswith(_PUBLICO) for u in urls), urls


def test_executavel_mais_velho_manda_instalar_a_versao_do_mcp(pecas):
    estado, _ = pecas
    estado["executable"] = "0.17.0"
    [aviso] = V.version_warnings(object())
    assert "v0.18.0/novomodelo-cli-installer" in aviso and "install_novomodelo" in aviso


def test_bridge_instalado_a_parte_e_mais_novo_da_os_dois_caminhos(pecas):
    estado, _ = pecas
    estado["bridge"] = "0.18.1"
    [aviso] = V.version_warnings(object())
    assert aviso.startswith("O novomodelo-bridge está na 0.18.1 e o MCP na 0.18.0;")
    assert V.mcp_install_command("0.18.1") in aviso and "novomodelo-bridge==0.18.0" in aviso


_REBAIXAR = re.compile(r"volte|voltar|rebaix|downgrade|mantenha", re.I)


def test_bridge_do_pacote_atras_tem_o_comando_do_mcp(pecas, monkeypatch):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    _bridge_do_pacote(monkeypatch)
    [aviso] = V.version_warnings(object())
    assert V.mcp_install_command("0.18.0") in aviso


@pytest.mark.parametrize("executavel", ["0.17.0", "0.18.0", "0.18.1", None])
@pytest.mark.parametrize("bridge", ["0.17.0", "0.18.0", "0.18.1"])
def test_nenhum_aviso_manda_instalar_versao_diferente_da_do_mcp(pecas, executavel, bridge):
    estado, _ = pecas
    estado.update(executable=executavel, bridge=bridge)
    texto = " ".join(V.version_warnings(object()))
    for outra in ("0.17.0", "0.18.1"):
        sem_o_mcp = texto.replace(V.mcp_install_command(outra), "")
        assert f"v{outra}/novomodelo-cli-installer" not in texto and f"=={outra}" not in sem_o_mcp


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
    sem = sorted(t.name for t in tools if not getattr(t.fn, "_version_warnings", False))
    assert sem == []


@pytest.mark.parametrize(
    "tool,args",
    [
        ("run_status", {"job_id": "nao-existe"}),
        ("schema_list", {}),
        ("results_list_entities", {"output_dir": "/nao/existe"}),
    ],
)
def test_bridge_017_aparece_em_tools_sem_cap_envelope(pecas, sem_rede, monkeypatch, tool, args):
    estado, _ = pecas
    estado["bridge"] = "0.17.0"
    monkeypatch.delenv("NOVOMODELO_MCP_WORKSPACE", raising=False)
    fn = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}[tool]
    env = fn(**args)
    assert any("novomodelo-bridge==0.18.0" in a for a in env["version_warnings"])
    assert sem_rede == []


def test_com_tudo_018_o_campo_nao_aparece(pecas, sem_rede):
    fn = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}["schema_list"]
    assert "version_warnings" not in fn()


def test_embrulho_preserva_o_schema_publicado():
    tools = {t.name: t for t in build_server()._tool_manager.list_tools()}
    fmt = tools["bridge_compare_newave"].parameters["properties"]["fmt"]
    assert fmt["enum"] == ["console", "html", "csv", "parquet", "json", "all"]


def test_aviso_que_quebra_nao_derruba_a_tool(monkeypatch):
    monkeypatch.setattr(V, "_read_local", lambda settings: 1 / 0)
    fn = {t.name: t.fn for t in build_server()._tool_manager.list_tools()}["schema_list"]
    assert fn()["status"] == "ok"


# ── rede: domínios, contexto TLS, falhas ──────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/ons-ccee-epe/novomodelo/releases/download/v0.18.0/x",
        "https://api.github.com/repos/ons-ccee-epe/novomodelo/releases/latest",
        "https://pypi.org/pypi/novomodelo-bridge/json",
        "https://pypi.org/pypi/novomodelo-mcp/json",
    ],
)
def test_dominios_permitidos(url):
    assert V.allowed_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/ons-ccee-epe/novomodelo",
        "https://github.com/outra-org/novomodelo",
        "https://api.github.com/repos/outra-org/novomodelo-mcp/releases/latest",
        "https://pypi.org/pypi/outro-pacote/json",
        "https://release-assets.githubusercontent.com/x",
        "https://evil.example/ons-ccee-epe/",
    ],
)
def test_dominios_recusados(url):
    assert not V.allowed_url(url)


def test_redirecionamento_so_para_o_cdn_do_github():
    assert V.allowed_url("https://release-assets.githubusercontent.com/x", redirect=True)
    assert not V.allowed_url("https://evil.example/x", redirect=True)


def test_url_fora_da_lista_e_recusada_sem_abrir_conexao(sem_rede):
    r = V.fetch_json("https://evil.example/x.json", timeout=1)
    assert r["network_warning"] and "não permitido" in r["network_warning"] and sem_rede == []


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


def test_falha_de_certificado_vira_network_warning(monkeypatch):
    def _cert(req, *, timeout, context):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("self-signed certificate"))

    monkeypatch.setattr(V, "_open", _cert)
    r = V.fetch_json("https://pypi.org/pypi/novomodelo-bridge/json", timeout=1)
    assert "certificado" in r["network_warning"]


# ── versão nova no server_info ────────────────────────────────────────────────

NOTAS = """## Release Notes

### Added

- A new thing that is not a change.

### Changed

- The training gap is printed with 5 decimals instead of 1.
- **BREAKING:** the default of `modeling.inflow_non_negativity.method` is now
  `truncation_with_penalty` (was `penalty`).
- `novomodelo run` writes its report to stdout; warnings and errors stay on stderr.

### Fixed

- `truncation` no longer produces an infeasible LP.

# novomodelo-cli 0.19.0

## Install novomodelo-cli 0.19.0

- not a change either
"""


def _respostas(
    monkeypatch,
    tag="v0.19.0",
    bridge="0.19.0",
    atraso=0.0,
    notas=NOTAS,
    notas_bridge=NOTAS,
    tag_bridge=None,
    mcp=None,
):
    def _abrir(req, *, timeout, context):
        time.sleep(atraso)
        url = req.full_url
        if "/pypi/novomodelo-mcp/" in url:
            if mcp is None:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            corpo = {"info": {"version": mcp}}
        elif "novomodelo-bridge/releases" in url:
            t = tag_bridge or f"v{bridge}"
            corpo = {
                "tag_name": t,
                "body": notas_bridge,
                "html_url": f"https://github.com/ons-ccee-epe/novomodelo-bridge/releases/tag/{t}",
            }
        elif "api.github.com" in url:
            corpo = {
                "tag_name": tag,
                "body": notas,
                "html_url": f"https://github.com/ons-ccee-epe/novomodelo/releases/tag/{tag}",
            }
        else:
            corpo = {"info": {"version": bridge}}
        return json.dumps(corpo).encode()

    monkeypatch.setattr(V, "_open", _abrir)


def test_mudancas_sao_changed_e_fixed_com_breaking_primeiro():
    linhas = V.release_changes(NOTAS)
    assert linhas[0] == (
        "BREAKING: the default of `modeling.inflow_non_negativity.method` is "
        "now `truncation_with_penalty` (was `penalty`)."
    )
    assert linhas[1:] == [
        "The training gap is printed with 5 decimals instead of 1.",
        "`novomodelo run` writes its report to stdout; warnings and errors stay on stderr.",
        "`truncation` no longer produces an infeasible LP.",
    ]


def test_mudancas_tem_teto_de_linhas_e_de_caracteres():
    corpo = "### Changed\n\n" + "".join(f"- item {i} " + "x" * 400 + "\n" for i in range(30))
    linhas = V.release_changes(corpo)
    assert len(linhas) == V.NOTES_MAX_LINES + 1 and linhas[-1].startswith("(mais ")
    assert all(len(linha) <= V.NOTES_MAX_LINE_CHARS for linha in linhas)
    assert sum(len(linha) for linha in linhas) <= V.NOTES_MAX_CHARS
    assert V.release_changes("") == [] and V.release_changes(None) == []


def test_versao_nova_traz_as_mudancas_e_o_link_das_notas(pecas, monkeypatch):
    _respostas(monkeypatch)
    nova = V.update_check(object())
    assert nova["novomodelo"]["release_changes"][0].startswith("BREAKING:")
    assert nova["novomodelo"]["release_notes"].endswith("/novomodelo/releases/tag/v0.19.0")
    assert nova["bridge"]["release_changes"] == V.release_changes(NOTAS)
    assert nova["bridge"]["release_notes"].endswith("/novomodelo-bridge/releases/tag/v0.19.0")


def test_sem_notas_legiveis_so_o_link(pecas, monkeypatch):
    _respostas(monkeypatch, notas="", tag_bridge="v0.18.9")
    nova = V.update_check(object())
    assert "release_changes" not in nova["novomodelo"]
    assert nova["novomodelo"]["release_notes"] == f"{V.CLI_RELEASES}/tag/v0.19.0"
    assert "release_changes" not in nova["bridge"]
    assert nova["bridge"]["release_notes"] == f"{V.BRIDGE_RELEASES}/tag/v0.19.0"


def test_aviso_de_peca_mais_nova_traz_as_mudancas_guardadas(pecas, monkeypatch):
    estado, _ = pecas
    estado["executable"] = "0.19.0"
    [sem_consulta] = V.version_warnings(object())
    assert f"Notas da 0.19.0: {V.CLI_RELEASES}/tag/v0.19.0" in sem_consulta
    assert "BREAKING" not in sem_consulta
    _respostas(monkeypatch)
    V.update_check(object())
    [com_consulta] = V.version_warnings(object())
    assert "Mudanças da 0.19.0:\n- BREAKING: the default" in com_consulta
    assert "\n- `truncation` no longer produces an infeasible LP." in com_consulta
    assert f"Notas: {V.CLI_RELEASES}/tag/v0.19.0" in com_consulta


def test_release_mais_novo_nao_da_o_mcp_novo_como_existente(pecas, monkeypatch):
    _respostas(monkeypatch)
    mcp = V.update_check(object())["mcp"]
    assert mcp["status"] == "a_conferir" and "link" not in mcp and "command" not in mcp
    assert "MCP 0.19.0" in mcp["note"] and V.mcp_install_command("0.19.0") in mcp["note"]


def test_mcp_novo_no_pypi_vem_com_o_comando_e_as_notas_do_proprio_repo(pecas, monkeypatch):
    _respostas(monkeypatch, mcp="0.19.0")
    mcp = V.update_check(object())["mcp"]
    assert mcp["status"] == "nova" and mcp["latest"] == "0.19.0"
    assert mcp["command"] == V.mcp_install_command("0.19.0")
    assert (
        mcp["release_notes"]
        == "https://github.com/ons-ccee-epe/novomodelo-mcp/releases/tag/v0.19.0"
    )


def test_mcp_no_pypi_na_versao_atual_nao_sugere_atualizar(pecas, monkeypatch):
    _respostas(monkeypatch, tag="v0.18.0", bridge="0.18.0", mcp="0.18.0")
    mcp = V.update_check(object())["mcp"]
    assert mcp["status"] == "atual" and "command" not in mcp


def test_release_mais_novo_nao_manda_instalar_so_o_executavel(pecas, monkeypatch):
    _respostas(monkeypatch)
    nova = V.update_check(object())
    assert nova["novomodelo"]["status"] == "nova" and nova["novomodelo"]["latest"] == "0.19.0"
    assert "command" not in nova["novomodelo"]
    assert "o MCP está na 0.18.0" in nova["novomodelo"]["note"]
    assert "command" not in nova["bridge"] and nova["bridge"]["latest"] == "0.19.0"
    assert not any(_REBAIXAR.search(p.get("note", "")) for p in nova.values())


def test_versao_atual_nao_sugere_atualizar(pecas, monkeypatch):
    _respostas(monkeypatch, tag="v0.18.0", bridge="0.18.0")
    nova = V.update_check(object())
    assert nova["novomodelo"]["status"] == "atual" and "command" not in nova["novomodelo"]


def test_sem_rede_nao_foi_possivel_verificar_em_menos_de_3s(pecas, monkeypatch):
    def _cai(req, *, timeout, context):
        raise urllib.error.URLError("sem rede")

    monkeypatch.setattr(V, "_open", _cai)
    t0 = time.perf_counter()
    nova = V.update_check(object())
    assert time.perf_counter() - t0 < 3
    assert nova["novomodelo"]["status"] == "nao_foi_possivel_verificar"
    assert nova["novomodelo"]["network_warning"]


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
    assert len(chamadas) == 4  # MCP e bridge no PyPI, novomodelo e notas do bridge, uma vez nas 6 h
    agora[0] += 2
    V.update_check(object())
    assert len(chamadas) == 8  # passadas as 6 h, consulta de novo (e as notas junto)


def test_docs_de_outra_versao_avisam_e_sem_manifesto_nao(pecas, monkeypatch):
    estado, _ = pecas
    ler = V._read_local
    monkeypatch.setattr(V, "_read_local", lambda s: ler(s) | {"docs": {"version": "0.17.0"}})
    assert any("docs embutidas na versão 0.17.0" in a for a in V.version_warnings(object()))
    V.reset_caches()
    monkeypatch.setattr(V, "_read_local", ler)
    assert V.version_warnings(object()) == []


def test_docs_embutidas_reais_tem_a_versao_do_manifesto():
    piece = V._docs_piece()
    assert piece["version"] and piece["commit"]


def test_comando_de_instalar_o_mcp_compila_o_bytecode():
    assert V.mcp_install_command("0.19.0") == (
        "`uv tool install --force --compile-bytecode novomodelo-mcp==0.19.0` "
        "(o bridge, a biblioteca e as docs vêm junto)"
    )
