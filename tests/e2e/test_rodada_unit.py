"""Rodada com executor, motor, determinística e gitleaks falsos: sem container nem agente."""

from __future__ import annotations

import _thread
import hashlib
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from tests.e2e import __main__ as cli
from tests.e2e import rodada
from tests.e2e.config import Config
from tests.e2e.conjuntos.usuario.juiz import JUIZ_PADRAO, LimiteDeUsoJuiz
from tests.e2e.executor import container
from tests.e2e.executor.container import Execucao, Saida
from tests.e2e.executor.eventos import Leitura
from tests.e2e.executor.imagens import CHAVE_DO_AGENTE, ConfigMCP, ler_config_mcp, tag_imagem
from tests.e2e.executor.mascara import MASCARA, mascarar
from tests.e2e.resultado.armazenamento import gravar_registro, ler_manifesto, ler_registros
from tests.e2e.resultado.modelos import Registro

TOKEN_FALSO = "sk-ant-oat01-FALSO-FALSO-FALSO"
LEITURA = ("deck_list", "server_info")


def _cfg(tmp_path: Path, extra: Path | None = None) -> Config:
    (tmp_path / "cache" / "preparados" / "exemplo_1dtoy").mkdir(parents=True, exist_ok=True)
    return Config(
        motor="podman",
        resultados=tmp_path / "res",
        casos=None,
        cenarios_extra=extra,
        token_claude=tmp_path / "token",
        volume_kiro="vol",
        cache=tmp_path / "cache",
    )


def _wheel(tmp_path: Path, versao: str = "1.2.3", conteudo: bytes = b"wheel") -> ConfigMCP:
    arquivo = tmp_path / "wheels" / versao / f"novomodelo_mcp-{versao}-py3-none-any.whl"
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(conteudo)
    return ler_config_mcp(str(arquivo))


class Falsos:
    """O executor e as dependências de fora do processo, com o que cada um recebeu."""

    def __init__(self, limites: dict[str, int] | None = None, det: str = "passou") -> None:
        self.execucoes: list[Execucao] = []
        self.esperas: list[float] = []
        self.varridas: list[Path] = []
        self.limites = dict(limites or {})
        self.det = det
        self.agora = 0.0
        self.passo = 0.0
        self.log_com_token = False
        self.det_chamadas = 0
        self.antes_de_executar = None
        self.encerrados: list[list[str]] = []

    def executar(self, e: Execucao, cfg: Config, pasta: Path, avaliar) -> Registro:
        self.execucoes.append(e)
        if self.antes_de_executar is not None:
            self.antes_de_executar(e)
        chave = rodada._rotulo(e)
        motivo = "ok"
        if self.limites.get(chave, 0) > 0:
            self.limites[chave] -= 1
            motivo = rodada.MOTIVO_LIMITE_AGENTE
        r = Registro(
            rodada=pasta.name,
            conjunto=e.conjunto,
            caso=e.caso,
            agente=e.agente,
            config=e.config,
            repeticao=e.repeticao,
            estado="erro_infra" if motivo != "ok" else "passou",
            motivo=motivo,
            tools=(),
            duracao_s=1.0,
        )
        gravar_registro(pasta, r)
        if self.log_com_token:
            (rodada._pasta_da_execucao(pasta, e) / "log.jsonl").write_text(
                f'{{"texto": "{TOKEN_FALSO}"}}\n', encoding="utf-8"
            )
        return r

    def construir(self, c: ConfigMCP, agente: str, cfg: Config) -> dict[str, str]:
        versoes = {"novomodelo": "1.0.0", "novomodelo-bridge": "1.0.0"}
        versoes[CHAVE_DO_AGENTE[agente]] = "9.9.9"
        if c.wheel is not None:
            versoes[f"mcp:{c.nome}"] = c.nome.removeprefix("mcp-")
        return versoes

    def leitura(self, c: ConfigMCP, agente: str, cfg: Config) -> tuple[str, ...]:
        return LEITURA if c.wheel is not None else ()

    def deterministica(self, pasta: Path, cfg: Config) -> list[Registro]:
        self.det_chamadas += 1
        return [rodada._registro_deterministica(pasta.name, "test_x", self.det, self.det, 0.1)]

    def varrer(self, pasta: Path) -> rodada.Varredura:
        self.varridas.append(pasta)
        com_token = [
            a.relative_to(pasta).as_posix()
            for a in sorted(pasta.rglob("*"))
            if a.is_file() and TOKEN_FALSO in a.read_text(encoding="utf-8")
        ]
        return rodada.Varredura(tuple(com_token))

    def relogio(self) -> float:
        self.agora += self.passo
        return self.agora

    def esperar(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.agora += segundos

    def dep(self) -> rodada.Dependencias:
        return rodada.Dependencias(
            executar=self.executar,
            construir=self.construir,
            leitura_mcp=self.leitura,
            deterministica=self.deterministica,
            varrer=self.varrer,
            commit=lambda: "abc1234",
            relogio=self.relogio,
            esperar=self.esperar,
            encerrar_em_voo=self.encerrar_em_voo,
        )

    def encerrar_em_voo(self, cfg: Config, prefixos) -> list[str]:
        self.encerrados.append(list(prefixos))
        return list(prefixos)


def _rodar(f: Falsos, cfg: Config, configs, **kw) -> Path:
    base = {
        "rodada": "r1",
        "conjuntos": ["usuario"],
        "agentes": ["claude"],
        "repeticoes": 1,
        "filtro": "i01*",
        "paralelo_por_agente": 1,
    }
    base.update(kw)
    return rodada.rodar(
        base.pop("rodada"),
        configs,
        base.pop("conjuntos"),
        base.pop("agentes"),
        base.pop("repeticoes"),
        cfg,
        base.pop("orcamento", rodada.ORCAMENTO_PADRAO),
        base.pop("paralelo_por_agente"),
        dep=f.dep(),
        **base,
    )


def _agentes(pasta: Path) -> list[Registro]:
    return [r for r in ler_registros(pasta) if r.conjunto != "deterministica"]


def test_padrao_e_dois_conjuntos_dois_agentes_tres_repeticoes(tmp_path, monkeypatch):
    recebido = {}
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))
    monkeypatch.setattr(cli, "verificar", lambda cfg: [])
    monkeypatch.setattr(
        rodada, "rodar", lambda *a, **kw: recebido.update(a=a, kw=kw) or tmp_path / "r"
    )
    wheel = _wheel(tmp_path)
    assert cli.main(["rodar", "--mcp", str(wheel.wheel)]) == 0
    configs, conjuntos, agentes, repeticoes, _, orcamento, paralelo = recebido["a"][1:]
    assert [c.nome for c in configs] == ["mcp-1.2.3"]
    assert conjuntos == ["tools", "usuario"]
    assert agentes == ["claude", "kiro"]
    assert repeticoes == 3
    assert orcamento == rodada.Orcamento(2000, 240)
    assert paralelo == 3

    planejadas = rodada.planejar(
        configs, conjuntos, agentes, repeticoes, _cfg(tmp_path), "bridge-check-newave-valid,i01*"
    )
    assert len(planejadas) == 2 * 2 * 3
    assert {p.execucao.conjunto for p in planejadas} == {"tools", "usuario"}


def test_completa_acrescenta_sem_mcp(tmp_path, monkeypatch):
    recebido = {}
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))
    monkeypatch.setattr(cli, "verificar", lambda cfg: [])
    monkeypatch.setattr(rodada, "rodar", lambda *a, **kw: recebido.update(a=a, kw=kw) or tmp_path)
    wheel = _wheel(tmp_path)
    assert cli.main(["rodar", "--mcp", str(wheel.wheel), "--completa"]) == 0
    assert [c.nome for c in recebido["a"][1]] == ["mcp-1.2.3", "sem-mcp"]
    assert recebido["kw"]["completa"] is True


def test_conjunto_tools_so_roda_com_mcp(tmp_path):
    configs = [_wheel(tmp_path), ler_config_mcp("sem")]
    planejadas = rodada.planejar(
        configs, ["tools"], ["claude"], 1, _cfg(tmp_path), "bridge-check-newave-valid"
    )
    assert [p.execucao.config for p in planejadas] == ["mcp-1.2.3"]


def test_deterministica_falha_para_antes_dos_agentes(tmp_path):
    f = Falsos(det="falhou")
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(f, _cfg(tmp_path), [_wheel(tmp_path)])
    assert erro.value.codigo == rodada.CODIGO_DETERMINISTICA
    assert f.execucoes == []
    pasta = erro.value.pasta
    assert [r.conjunto for r in ler_registros(pasta)] == ["deterministica"]
    assert f.varridas == [pasta]


def test_retomada_refaz_execucao_sem_registro(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    pasta = _rodar(f, cfg, configs, repeticoes=2)
    assert len(f.execucoes) == 2
    apagado = rodada._pasta_da_execucao(pasta, f.execucoes[1]) / "registro.json"
    apagado.unlink()
    f.execucoes.clear()
    _rodar(f, cfg, configs, repeticoes=2)
    assert [e.repeticao for e in f.execucoes] == [2]
    assert len(_agentes(pasta)) == 2


def test_retomada_com_outro_plano_e_recusada(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    _rodar(f, cfg, configs)
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(f, cfg, configs, repeticoes=2)
    assert erro.value.codigo == rodada.CODIGO_RECUSA


def test_caso_ausente_vira_pulado(tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "x01.toml").write_text(
        'id = "x01-grande"\npersona = "consultoria"\ncaso = "caso_grande_newave"\n'
        'pedido = "converta"\ntools_esperadas = ["bridge_convert_newave"]\n',
        encoding="utf-8",
    )
    f = Falsos()
    pasta = _rodar(f, _cfg(tmp_path, extra), [_wheel(tmp_path)], filtro="x01*")
    assert f.execucoes == []
    [r] = _agentes(pasta)
    assert (r.caso, r.estado) == ("x01-grande", "pulado")
    assert "caso_grande_newave" in r.motivo


def test_orcamento_estourado_para_e_grava_o_que_fez(tmp_path):
    f = Falsos()
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(
            f, _cfg(tmp_path), [_wheel(tmp_path)], repeticoes=4, orcamento=rodada.Orcamento(2, 0)
        )
    assert erro.value.codigo == rodada.CODIGO_ORCAMENTO
    assert len(_agentes(erro.value.pasta)) == 2
    assert ler_manifesto(erro.value.pasta).repeticoes == 4
    assert f.varridas


def test_orcamento_de_tempo_estourado_para(tmp_path):
    f = Falsos()
    f.passo = 61 * 60
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(
            f, _cfg(tmp_path), [_wheel(tmp_path)], repeticoes=3, orcamento=rodada.Orcamento(0, 60)
        )
    assert erro.value.codigo == rodada.CODIGO_ORCAMENTO
    assert f.execucoes == []


def test_sem_limite_com_zero(tmp_path, monkeypatch):
    f = Falsos()
    f.passo = 10 * 3600
    pasta = _rodar(
        f, _cfg(tmp_path), [_wheel(tmp_path)], repeticoes=3, orcamento=rodada.Orcamento(0, 0)
    )
    assert len(_agentes(pasta)) == 3

    recebido = {}
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))
    monkeypatch.setattr(cli, "verificar", lambda cfg: [])
    monkeypatch.setattr(rodada, "rodar", lambda *a, **kw: recebido.update(a=a) or tmp_path)
    argv = ["rodar", "--mcp", str(_wheel(tmp_path).wheel), "--max-execucoes", "0"]
    assert cli.main([*argv, "--max-minutos", "0"]) == 0
    assert recebido["a"][6] == rodada.Orcamento(0, 0)


def test_intercala_configuracoes(tmp_path):
    f = Falsos()
    configs = [_wheel(tmp_path, "1.0.0"), _wheel(tmp_path, "2.0.0")]
    _rodar(f, _cfg(tmp_path), configs, repeticoes=2, filtro="i01*,i02*")
    ordem = [(e.repeticao, e.caso, e.config) for e in f.execucoes]
    assert ordem == [
        (1, "i01-comecar", "mcp-1.0.0"),
        (1, "i01-comecar", "mcp-2.0.0"),
        (1, "i02-deck-o-que-faco", "mcp-1.0.0"),
        (1, "i02-deck-o-que-faco", "mcp-2.0.0"),
        (2, "i01-comecar", "mcp-1.0.0"),
        (2, "i01-comecar", "mcp-2.0.0"),
        (2, "i02-deck-o-que-faco", "mcp-1.0.0"),
        (2, "i02-deck-o-que-faco", "mcp-2.0.0"),
    ]


def test_rodada_com_token_no_log_bloqueia_relatorio(tmp_path):
    f = Falsos()
    f.log_com_token = True
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(f, _cfg(tmp_path), [_wheel(tmp_path)])
    assert erro.value.codigo == rodada.CODIGO_SEGREDO
    bloqueio = (erro.value.pasta / rodada.ARQUIVO_BLOQUEIO).read_text(encoding="utf-8")
    assert "log.jsonl" in bloqueio
    assert TOKEN_FALSO not in bloqueio


def test_varredura_que_nao_roda_bloqueia(tmp_path):
    f = Falsos()
    dep = f.dep()
    dep = rodada.Dependencias(
        **{**dep.__dict__, "varrer": lambda p: rodada.Varredura(erro="gitleaks fora do PATH")}
    )
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        rodada.rodar(
            "r1",
            [_wheel(tmp_path)],
            ["usuario"],
            ["claude"],
            1,
            _cfg(tmp_path),
            filtro="i01*",
            dep=dep,
        )
    assert erro.value.codigo == rodada.CODIGO_SEGREDO


@pytest.mark.parametrize("motivo", sorted(rodada.MOTIVOS_LIMITE))
def test_limite_de_uso_nao_grava_e_sai_com_4(tmp_path, motivo, monkeypatch):
    f = Falsos(limites={"usuario/i01-comecar/claude/mcp-1.2.3/1": 1})
    monkeypatch.setattr(rodada, "MOTIVO_LIMITE_AGENTE", motivo)
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(f, cfg, configs)
    assert erro.value.codigo == rodada.CODIGO_LIMITE
    pasta = erro.value.pasta
    assert _agentes(pasta) == []
    assert not rodada._pasta_da_execucao(pasta, f.execucoes[0]).exists()
    assert any(json.loads(linha)["evento"] == "limite" for linha in _log(pasta))
    f.execucoes.clear()
    _rodar(f, cfg, configs)
    assert len(f.execucoes) == 1
    assert [r.estado for r in _agentes(pasta)] == ["passou"]


def test_registro_de_limite_que_sobrou_e_refeito(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    pasta = _rodar(f, cfg, configs)
    arquivo = rodada._pasta_da_execucao(pasta, f.execucoes[0]) / "registro.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    limite = {**dados, "estado": "erro_infra", "motivo": rodada.MOTIVO_LIMITE_JUIZ}
    arquivo.write_text(json.dumps(limite), "utf-8")
    f.execucoes.clear()
    _rodar(f, cfg, configs)
    assert len(f.execucoes) == 1


def _log(pasta: Path) -> list[str]:
    return (pasta / rodada.ARQUIVO_LOG).read_text(encoding="utf-8").splitlines()


def test_esperar_limite_retoma_sozinho(tmp_path):
    f = Falsos(limites={"usuario/i01-comecar/claude/mcp-1.2.3/1": 2})
    pasta = _rodar(f, _cfg(tmp_path), [_wheel(tmp_path)], esperar_limite_min=15)
    assert f.esperas == [900, 900]
    assert len(f.execucoes) == 3
    assert [r.estado for r in _agentes(pasta)] == ["passou"]
    esperas = [json.loads(linha) for linha in _log(pasta)]
    esperas = [e for e in esperas if e["evento"] == "espera_limite"]
    assert [(e["minutos"], e["espera"]) for e in esperas] == [(15, 1), (15, 2)]


def test_motivos_de_limite_sao_os_do_executor_e_do_juiz():
    saida = Saida([], "Claude AI usage limit reached", 1, False)
    assert container._motivo_de_infra(saida, Leitura([])) == rodada.MOTIVO_LIMITE_AGENTE
    juiz = f"falha na execução: {container._descrever(LimiteDeUsoJuiz())}"
    assert juiz == rodada.MOTIVO_LIMITE_JUIZ


def test_manifesto_tem_sha256_e_origem_de_cada_wheel(tmp_path):
    f = Falsos()
    a = _wheel(tmp_path, "1.0.0", b"conteudo a")
    b = _wheel(tmp_path, "2.0.0", b"conteudo b")
    configs = [a, b, ler_config_mcp("sem")]
    pasta = _rodar(f, _cfg(tmp_path), configs, origens={"mcp-1.0.0": "release v1.0.0, commit 1"})
    m = ler_manifesto(pasta)
    assert m.wheels == {
        "mcp-1.0.0": {
            "arquivo": a.wheel.name,
            "sha256": hashlib.sha256(b"conteudo a").hexdigest(),
            "origem": "release v1.0.0, commit 1",
        },
        "mcp-2.0.0": {
            "arquivo": b.wheel.name,
            "sha256": hashlib.sha256(b"conteudo b").hexdigest(),
            "origem": rodada.ORIGEM_NAO_INFORMADA,
        },
    }
    assert set(m.imagens) == {tag_imagem(c, "claude") for c in configs}
    assert m.versoes["juiz-modelo"] == JUIZ_PADRAO.modelo
    assert "não tem opção de temperatura" in m.versoes["juiz-temperatura"]
    assert m.versoes["juiz-imagem"] == tag_imagem(a, "claude")
    assert m.versoes["kiro-cli"] == rodada.NAO_USADO
    assert m.commit_bateria == "abc1234"


def test_cli_origem_de_config_sem_wheel_e_recusada(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))
    monkeypatch.setattr(cli, "verificar", lambda cfg: [])
    wheel = _wheel(tmp_path)
    with pytest.raises(SystemExit) as saida:
        cli.main(["rodar", "--mcp", str(wheel.wheel), "--origem-mcp", "mcp-9.9=release"])
    assert saida.value.code == 2


def test_cli_sai_com_o_codigo_da_rodada(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "carregar_config", lambda env: _cfg(tmp_path))
    monkeypatch.setattr(cli, "verificar", lambda cfg: [])

    def para(*a, **kw):
        raise rodada.RodadaInterrompida(rodada.CODIGO_LIMITE, "limite", tmp_path)

    monkeypatch.setattr(rodada, "rodar", para)
    assert cli.main(["rodar", "--mcp", str(_wheel(tmp_path).wheel)]) == 4


def test_usuario_recebe_agente_leitura_imagem_e_log(tmp_path, monkeypatch):
    recebidos = []

    def avaliar_usuario(c, juiz, cfg, **kw):
        recebidos.append((c.id, juiz, kw))
        return lambda leitura: None

    monkeypatch.setattr(rodada, "avaliar_usuario", avaliar_usuario)
    f = Falsos()
    configs = [_wheel(tmp_path), ler_config_mcp("sem")]
    pasta = _rodar(f, _cfg(tmp_path), configs, agentes=["kiro"], repeticoes=2)
    por_config = {(kw["destino_log"], kw["repeticao"]): kw for _, _, kw in recebidos}
    assert len(por_config) == 4
    for e in f.execucoes:
        kw = por_config[(rodada._pasta_da_execucao(pasta, e), e.repeticao)]
        assert kw["agente"] == "kiro"
        assert kw["leitura_mcp"] == (LEITURA if e.config == "mcp-1.2.3" else ())
        assert kw["imagem"] == tag_imagem(configs[0], "claude")
        assert kw["destino_log"].is_relative_to(pasta / "execucoes" / "usuario")
    assert tag_imagem(configs[0], "claude") in ler_manifesto(pasta).imagens


def test_execucao_leva_montar_em_e_sem_output_do_cenario(tmp_path):
    (tmp_path / "cache" / "preparados" / "exemplo_1dtoy_rodado").mkdir(parents=True)
    planejadas = rodada.planejar(
        [_wheel(tmp_path)], ["usuario"], ["claude"], 1, _cfg(tmp_path), "c08*,c16*"
    )
    por_id = {p.execucao.caso: p.execucao for p in planejadas}
    assert por_id["c08-pasta-fora"].montar_em == "/mnt/outros"
    assert por_id["c16-reduzir-teste"].sem_output is True
    assert por_id["c08-pasta-fora"].liberar == ()


def test_registros_do_junit(tmp_path):
    junit = tmp_path / "j.xml"
    junit.write_text(
        '<testsuites><testsuite><testcase classname="tests.m" name="test_a" time="0.5"/>'
        '<testcase classname="tests.m" name="test_b[x y]" time="1">'
        '<failure message="quebrou"/></testcase>'
        '<testcase name="test_c"><skipped message="precisa de --com-rede"/></testcase>'
        "</testsuite></testsuites>",
        encoding="utf-8",
    )
    registros = rodada.registros_do_junit(junit, "r1")
    assert [(r.caso, r.estado) for r in registros] == [
        ("tests.m.test_a", "passou"),
        ("tests.m.test_b-x-y", "falhou"),
        ("test_c", "pulado"),
    ]
    assert {r.conjunto for r in registros} == {"deterministica"}


def test_deterministica_usa_os_decks_do_cache(tmp_path):
    cfg = _cfg(tmp_path)
    for nome in ("bridge_newave_mini", "bridge_decomp_mini"):
        (cfg.cache / "preparados" / nome).mkdir(parents=True)
    pasta = tmp_path / "res" / "r1"
    chamadas = []

    def rodar(cmd, **kw):
        chamadas.append(cmd)
        junit = Path(next(a for a in cmd if a.startswith("--junitxml=")).split("=", 1)[1])
        junit.write_text('<testsuite><testcase name="test_a"/></testsuite>', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    registros = rodada.rodar_deterministica(pasta, cfg, rodar=rodar)
    [cmd] = chamadas
    assert "--executaveis-reais" in cmd and rodada.TESTE_DETERMINISTICA in cmd
    assert cmd[cmd.index("--newave-src") + 1] == str(
        cfg.cache / "preparados" / "bridge_newave_mini"
    )
    assert cmd[cmd.index("--decomp-src") + 1] == str(
        cfg.cache / "preparados" / "bridge_decomp_mini"
    )
    assert [r.estado for r in registros] == ["passou"]


def test_deterministica_sem_junit_vira_erro_infra(tmp_path):
    def rodar(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 4, "", "erro de uso")

    registros = rodada.rodar_deterministica(tmp_path / "r1", _cfg(tmp_path), rodar=rodar)
    assert [(r.caso, r.estado) for r in registros] == [("pytest", "erro_infra")]


def test_leitura_mcp_le_da_imagem(tmp_path):
    c = _wheel(tmp_path)
    chamadas = []

    def rodar(cmd, **kw):
        chamadas.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, 'aviso\n["deck_list", "server_info"]\n', "")

    assert rodada.ler_leitura_mcp(c, "claude", _cfg(tmp_path), rodar=rodar) == LEITURA
    assert "--network=none" in chamadas[0] and tag_imagem(c, "claude") in chamadas[0]
    assert rodada.ler_leitura_mcp(ler_config_mcp("sem"), "claude", _cfg(tmp_path)) == ()


FORMATOS_TOKEN = ("oat", "api", "admin")


def _token_falso(formato: str) -> str:
    return "sk-ant-" + formato + "01-" + "FalsoDeTeste" + "0" * 16


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks fora do PATH")
def test_gitleaks_real_reconhece_o_token_do_claude_em_cada_formato(tmp_path):
    pasta = tmp_path / "rodada"
    for formato in FORMATOS_TOKEN:
        destino = pasta / "execucoes" / formato
        destino.mkdir(parents=True)
        (destino / "log.jsonl").write_text(
            json.dumps({"texto": _token_falso(formato)}) + "\n", encoding="utf-8"
        )
    (pasta / "limpo.txt").write_text("nada aqui\n", encoding="utf-8")
    varredura = rodada.varrer_segredos(pasta)
    assert varredura.erro is None
    assert varredura.arquivos == tuple(f"execucoes/{f}/log.jsonl" for f in sorted(FORMATOS_TOKEN))


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks fora do PATH")
def test_gitleaks_real_pasta_limpa_nao_bloqueia(tmp_path):
    (tmp_path / "registro.json").write_text('{"estado": "passou"}', encoding="utf-8")
    assert rodada.varrer_segredos(tmp_path) == rodada.Varredura()


def test_varredura_passa_a_config_do_repo_e_cwd_temporario(tmp_path, monkeypatch):
    chamadas = []

    def run(cmd, **kw):
        chamadas.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(rodada.shutil, "which", lambda nome: "/bin/gitleaks-falso")
    monkeypatch.setattr(rodada.subprocess, "run", run)
    assert rodada.varrer_segredos(tmp_path) == rodada.Varredura()
    [(cmd, kw)] = chamadas
    assert cmd[cmd.index("--config") + 1] == str(rodada.CONFIG_GITLEAKS)
    assert rodada.CONFIG_GITLEAKS.is_file()
    assert Path(kw["cwd"]) != Path.cwd() and not Path(kw["cwd"]).is_relative_to(tmp_path)


def test_config_do_gitleaks_ausente_bloqueia(tmp_path, monkeypatch):
    monkeypatch.setattr(rodada.shutil, "which", lambda nome: "/bin/gitleaks-falso")
    varredura = rodada.varrer_segredos(tmp_path, config=tmp_path / "nao-existe.toml")
    assert varredura.erro and "config" in varredura.erro


@pytest.mark.parametrize("formato", FORMATOS_TOKEN)
def test_mascara_troca_o_token_de_cada_formato(formato):
    saida = mascarar(f"eco {_token_falso(formato)} fim")
    assert _token_falso(formato) not in saida and MASCARA in saida


def test_retomada_com_outro_filtro_e_recusada(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    pasta = _rodar(f, cfg, configs)
    assert ler_manifesto(pasta).filtro == "i01*"
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(f, cfg, configs, filtro="i02*")
    assert erro.value.codigo == rodada.CODIGO_RECUSA
    assert "filtro" in str(erro.value)


def test_retomada_com_outro_commit_e_recusada(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    _rodar(f, cfg, configs)
    dep = rodada.Dependencias(**{**f.dep().__dict__, "commit": lambda: "def5678"})
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        rodada.rodar("r1", configs, ["usuario"], ["claude"], 1, cfg, filtro="i01*", dep=dep)
    assert erro.value.codigo == rodada.CODIGO_RECUSA
    assert "commit" in str(erro.value)


def test_espera_do_limite_nao_conta_no_orcamento_de_tempo(tmp_path):
    f = Falsos(limites={"usuario/i01-comecar/claude/mcp-1.2.3/1": 2})
    pasta = _rodar(
        f,
        _cfg(tmp_path),
        [_wheel(tmp_path)],
        esperar_limite_min=15,
        orcamento=rodada.Orcamento(0, 20),
    )
    assert f.esperas == [900, 900]
    assert [r.estado for r in _agentes(pasta)] == ["passou"]


def test_execucao_apagada_por_limite_nao_conta_no_orcamento(tmp_path):
    f = Falsos(limites={"usuario/i01-comecar/claude/mcp-1.2.3/1": 1})
    pasta = _rodar(
        f,
        _cfg(tmp_path),
        [_wheel(tmp_path)],
        esperar_limite_min=1,
        orcamento=rodada.Orcamento(1, 0),
    )
    assert len(f.execucoes) == 2
    assert [r.estado for r in _agentes(pasta)] == ["passou"]


def test_tres_limites_seguidos_na_mesma_execucao_saem_com_4(tmp_path):
    f = Falsos(limites={"usuario/i01-comecar/claude/mcp-1.2.3/1": 99})
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        _rodar(f, _cfg(tmp_path), [_wheel(tmp_path)], esperar_limite_min=1)
    assert erro.value.codigo == rodada.CODIGO_LIMITE
    assert len(f.execucoes) == rodada.LIMITES_SEGUIDOS
    assert len(f.esperas) == rodada.LIMITES_SEGUIDOS - 1
    eventos = [json.loads(linha)["evento"] for linha in _log(erro.value.pasta)]
    assert "limite_repetido" in eventos


def test_limite_que_alterna_com_execucao_concluida_nao_atinge_o_teto(tmp_path):
    rotulo = "usuario/i01-comecar/claude/mcp-1.2.3/{}"
    f = Falsos(limites={rotulo.format(1): 2, rotulo.format(2): 2})
    pasta = _rodar(f, _cfg(tmp_path), [_wheel(tmp_path)], repeticoes=2, esperar_limite_min=1)
    assert [r.estado for r in _agentes(pasta)] == ["passou", "passou"]


def test_registro_com_motivo_de_limite_mas_sem_erro_infra_e_resultado(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    pasta = _rodar(f, cfg, configs)
    arquivo = rodada._pasta_da_execucao(pasta, f.execucoes[0]) / "registro.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    arquivo.write_text(json.dumps({**dados, "motivo": rodada.MOTIVO_LIMITE_AGENTE}), "utf-8")
    f.execucoes.clear()
    _rodar(f, cfg, configs)
    assert f.execucoes == []


def test_pasta_sem_registro_e_apagada_antes_de_refazer(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    pasta = _rodar(f, cfg, configs)
    destino = rodada._pasta_da_execucao(pasta, f.execucoes[0])
    (destino / "registro.json").unlink()
    (destino / "juiz.jsonl").write_text('{"tentativa": 1}\n', encoding="utf-8")
    vistos = []
    f.antes_de_executar = lambda e: vistos.append((destino / "juiz.jsonl").exists())
    _rodar(f, cfg, configs)
    assert vistos == [False]


def test_ctrl_c_encerra_containers_em_voo_varre_e_retoma(tmp_path):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    liberado = threading.Event()
    sobra = cfg.resultados / "r1" / ".trabalho-sobra"

    def interromper(e):
        sobra.mkdir(parents=True, exist_ok=True)
        _thread.interrupt_main()
        assert liberado.wait(10)

    def encerrar(cfg_, prefixos):
        f.encerrados.append(list(prefixos))
        liberado.set()
        return list(prefixos)

    f.antes_de_executar = interromper
    dep = rodada.Dependencias(**{**f.dep().__dict__, "encerrar_em_voo": encerrar})
    with pytest.raises(rodada.RodadaInterrompida) as erro:
        rodada.rodar(
            "r1",
            configs,
            ["usuario"],
            ["claude"],
            1,
            cfg,
            rodada.ORCAMENTO_PADRAO,
            1,
            filtro="i01*",
            dep=dep,
        )
    assert erro.value.codigo == rodada.CODIGO_INTERROMPIDA
    [prefixos] = f.encerrados
    assert prefixos == [rodada.prefixo_do_container(f.execucoes[0], "r1")]
    assert f.varridas == [erro.value.pasta]
    assert _agentes(erro.value.pasta) == []
    assert "interrompida" in [json.loads(linha)["evento"] for linha in _log(erro.value.pasta)]

    f.antes_de_executar = None
    f.execucoes.clear()
    pasta = _rodar(f, cfg, configs)
    assert not sobra.exists()
    assert [r.estado for r in _agentes(pasta)] == ["passou"]


def test_prefixo_do_container_e_o_nome_do_executor_sem_o_sufixo(tmp_path):
    [p] = rodada.planejar([_wheel(tmp_path)], ["usuario"], ["claude"], 1, _cfg(tmp_path), "i01*")
    nome = container.nome_container(p.execucao, "r1")
    assert nome.startswith(rodada.prefixo_do_container(p.execucao, "r1") + "-")


def test_leitura_mcp_da_nome_ao_container_e_o_encerra(tmp_path):
    c = _wheel(tmp_path)
    encerrados = []

    def rodar(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(rodada.FalhaPreparo):
        rodada.ler_leitura_mcp(
            c, "claude", _cfg(tmp_path), rodar=rodar, encerrar=lambda m, n: encerrados.append(n)
        )
    [nome] = encerrados
    assert nome.startswith("novomodelo-bateria-leitura-")


@pytest.mark.parametrize("estado", ["erro_infra", "corrompido", "sem_marca"])
def test_deterministica_refeita_na_retomada(tmp_path, estado):
    f = Falsos()
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    pasta = _rodar(f, cfg, configs)
    pasta_det = pasta / "execucoes" / "deterministica"
    [arquivo] = pasta_det.glob("*/*/*/*/registro.json")
    if estado == "erro_infra":
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        arquivo.write_text(json.dumps({**dados, "estado": "erro_infra"}), "utf-8")
    elif estado == "corrompido":
        arquivo.write_text("{quebrado", encoding="utf-8")
    else:
        (pasta_det / rodada.MARCA_DETERMINISTICA).unlink()
    _rodar(f, cfg, configs)
    assert f.det_chamadas == 2
    assert [r.estado for r in ler_registros(pasta) if r.conjunto == "deterministica"] == ["passou"]


def test_deterministica_com_falha_gravada_nao_roda_de_novo(tmp_path):
    f = Falsos(det="falhou")
    cfg = _cfg(tmp_path)
    configs = [_wheel(tmp_path)]
    for _ in range(2):
        with pytest.raises(rodada.RodadaInterrompida) as erro:
            _rodar(f, cfg, configs)
        assert erro.value.codigo == rodada.CODIGO_DETERMINISTICA
    assert f.det_chamadas == 1


def test_ajuda_da_cli_documenta_os_codigos_de_saida(capsys):
    with pytest.raises(SystemExit):
        cli.main(["rodar", "--help"])
    ajuda = " ".join(capsys.readouterr().out.split())
    for codigo in (0, 1, 2, 3, 4, 5):
        assert f"{codigo} " in ajuda
    assert "pulado" in ajuda
