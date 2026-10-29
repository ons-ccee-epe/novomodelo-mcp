"""Casos por nome lógico, decks do bridge e 1dtoy rodado, com git e motor falsos."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from novomodelo_mcp.adapters.versions import expected_version
from tests.e2e.config import Config
from tests.e2e.executor import casos
from tests.e2e.executor.casos import (
    CASOS_GRANDES,
    PUBLICOS,
    commit_esperado,
    pasta_preparados,
    preparar_1dtoy_rodado,
    preparar_decks,
    preparar_exemplo_1dtoy,
    resolver,
)
from tests.e2e.executor.container import ENDURECIMENTO, PASTA_ESTUDOS
from tests.e2e.executor.imagens import FalhaPreparo

RAIZ = Path(__file__).resolve().parents[3]
COMMIT = "a" * 40
OUTRO = "b" * 40
VERSAO = "9.8.7"


def _cfg(tmp_path: Path, casos_: Path | None = None) -> Config:
    return Config(
        motor="podman",
        resultados=tmp_path / "res",
        casos=casos_,
        cenarios_extra=None,
        token_claude=tmp_path / "token",
        volume_kiro="vol",
        cache=tmp_path / "cache",
    )


class GitFalso:
    """Imita `git clone`, `sparse-checkout` e `rev-parse` sem rede."""

    def __init__(self, commit: str, conteudo: tuple[str, ...], primeira_leitura: str | None = None):
        self.commit = commit
        self.primeira_leitura = primeira_leitura
        self.conteudo = conteudo
        self.chamadas: list[list[str]] = []

    def __call__(self, cmd, **kwargs):
        self.chamadas.append(list(cmd))
        assert cmd[0] == "git"
        assert isinstance(cmd, list)
        assert kwargs.get("timeout")
        assert not kwargs.get("shell")
        sub = cmd[1]
        if sub == "clone":
            destino = Path(cmd[-1])
            (destino / ".git").mkdir(parents=True)
            for caminho in self.conteudo:
                (destino / caminho).mkdir(parents=True, exist_ok=True)
                (destino / caminho / "arquivo.txt").write_text("x")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if sub == "rev-parse":
            lido, self.primeira_leitura = self.primeira_leitura or self.commit, None
            return subprocess.CompletedProcess(cmd, 0, f"{lido}\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def _decks() -> tuple[str, ...]:
    return ("tests/decks/newave_mini", "tests/decks/decomp_mini")


def test_resolver_publico(tmp_path):
    preparados = tmp_path / "preparados"
    (preparados / "bridge_newave_mini").mkdir(parents=True)
    cfg = _cfg(tmp_path)
    assert resolver("bridge_newave_mini", cfg, preparados) == preparados / "bridge_newave_mini"
    assert resolver("exemplo_1dtoy", cfg, preparados) is None


def test_resolver_caso_grande_ausente_e_none(tmp_path):
    preparados = tmp_path / "preparados"
    assert resolver("caso_grande_newave", _cfg(tmp_path), preparados) is None
    pasta = tmp_path / "casos"
    pasta.mkdir()
    assert resolver("caso_grande_newave", _cfg(tmp_path, pasta), preparados) is None


def test_resolver_caso_grande_presente(tmp_path):
    pasta = tmp_path / "casos"
    (pasta / "caso_grande_rodado").mkdir(parents=True)
    esperado = pasta / "caso_grande_rodado"
    assert resolver("caso_grande_rodado", _cfg(tmp_path, pasta), tmp_path) == esperado


def test_resolver_recusa_nome_desconhecido(tmp_path):
    with pytest.raises(ValueError, match="desconhecido"):
        resolver("../outro", _cfg(tmp_path), tmp_path)
    assert not PUBLICOS & CASOS_GRANDES


def test_decks_copia_os_dois_decks_na_tag_certa(tmp_path):
    cfg = _cfg(tmp_path)
    git = GitFalso(COMMIT, _decks())
    preparados = preparar_decks(VERSAO, COMMIT, cfg, rodar=git)
    assert (preparados / "bridge_newave_mini" / "arquivo.txt").is_file()
    assert (preparados / "bridge_decomp_mini" / "arquivo.txt").is_file()
    clone = git.chamadas[0]
    assert ["--depth", "1", "--branch", f"v{VERSAO}"] == clone[2:6]
    assert "--sparse" in clone and "--filter=blob:none" in clone


def test_decks_recusa_commit_diferente(tmp_path):
    cfg = _cfg(tmp_path)
    git = GitFalso(OUTRO, _decks())
    with pytest.raises(FalhaPreparo, match="commit esperado"):
        preparar_decks(VERSAO, COMMIT, cfg, rodar=git)
    assert not pasta_preparados(cfg).exists()
    assert not any(c[1] == "sparse-checkout" for c in git.chamadas)


def test_decks_reutiliza_o_cache_quando_o_commit_bate(tmp_path):
    cfg = _cfg(tmp_path)
    preparar_decks(VERSAO, COMMIT, cfg, rodar=GitFalso(COMMIT, _decks()))
    git = GitFalso(COMMIT, _decks())
    preparar_decks(VERSAO, COMMIT, cfg, rodar=git)
    assert not any(c[1] == "clone" for c in git.chamadas)


def test_decks_refaz_o_cache_quando_o_commit_nao_bate(tmp_path):
    cfg = _cfg(tmp_path)
    preparar_decks(VERSAO, COMMIT, cfg, rodar=GitFalso(COMMIT, _decks()))
    git = GitFalso(COMMIT, _decks(), primeira_leitura=OUTRO)
    preparar_decks(VERSAO, COMMIT, cfg, rodar=git)
    assert any(c[1] == "clone" for c in git.chamadas)


@pytest.mark.parametrize("versao,commit", [("--x", COMMIT), ("1.0", "abc"), ("1.0 ", COMMIT)])
def test_decks_recusa_versao_ou_commit_mal_formado(tmp_path, versao, commit):
    git = GitFalso(COMMIT, _decks())
    with pytest.raises(FalhaPreparo, match="inválido"):
        preparar_decks(versao, commit, _cfg(tmp_path), rodar=git)
    assert git.chamadas == []


def test_decks_ausentes_na_tag_viram_erro(tmp_path):
    with pytest.raises(FalhaPreparo, match="ausente"):
        preparar_decks(VERSAO, COMMIT, _cfg(tmp_path), rodar=GitFalso(COMMIT, ()))


def test_decks_git_com_erro_vira_falha_sem_vazar_a_saida(tmp_path):
    def rodar(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 128, "", "fatal: segredo")

    with pytest.raises(FalhaPreparo) as erro:
        preparar_decks(VERSAO, COMMIT, _cfg(tmp_path), rodar=rodar)
    assert "segredo" not in str(erro.value)


def test_exemplo_1dtoy_vem_do_repositorio_do_novomodelo(tmp_path):
    cfg = _cfg(tmp_path)
    git = GitFalso(COMMIT, ("examples/1dtoy",))
    destino = preparar_exemplo_1dtoy(VERSAO, COMMIT, cfg, rodar=git)
    assert destino == pasta_preparados(cfg) / "exemplo_1dtoy"
    assert (destino / "arquivo.txt").is_file()
    assert git.chamadas[0][-2].endswith("/novomodelo")


def test_1dtoy_rodado_roda_na_imagem_endurecida_sem_rede_e_(tmp_path):
    cfg = _cfg(tmp_path)
    exemplo = pasta_preparados(cfg) / "exemplo_1dtoy"
    exemplo.mkdir(parents=True)
    (exemplo / "config.json").write_text("{}")
    chamadas: list[list[str]] = []

    def motor(cmd, **kw):
        chamadas.append(list(cmd))
        assert kw["timeout"]
        montagem = next(c for c in cmd if c.startswith("type=bind"))
        origem = Path(montagem.split("src=")[1].split(",")[0])
        (origem / "output").mkdir()
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    destino = preparar_1dtoy_rodado("imagem:x", cfg, rodar=motor)
    assert destino == pasta_preparados(cfg) / "exemplo_1dtoy_rodado"
    assert (destino / "config.json").is_file() and (destino / "output").is_dir()
    assert not (exemplo / "output").exists()
    cmd = chamadas[0]
    assert set(ENDURECIMENTO) <= set(cmd) and "--network=none" in cmd
    assert cmd[-4:] == ["novomodelo", "run", f"{PASTA_ESTUDOS}/exemplo_1dtoy_rodado", "--quiet"]
    assert sorted(p.name for p in pasta_preparados(cfg).iterdir()) == [
        "exemplo_1dtoy",
        "exemplo_1dtoy_rodado",
    ]


def test_1dtoy_rodado_falha_do_motor_nao_deixa_destino(tmp_path):
    cfg = _cfg(tmp_path)
    (pasta_preparados(cfg) / "exemplo_1dtoy").mkdir(parents=True)

    def motor(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, b"", b"")

    with pytest.raises(FalhaPreparo, match="código 1"):
        preparar_1dtoy_rodado("imagem:x", cfg, rodar=motor)
    assert not (pasta_preparados(cfg) / "exemplo_1dtoy_rodado").exists()


def test_1dtoy_rodado_exige_o_exemplo_preparado(tmp_path):
    with pytest.raises(FalhaPreparo, match="não preparado"):
        preparar_1dtoy_rodado("imagem:x", _cfg(tmp_path), rodar=lambda *a, **k: None)


def test_fontes_tem_o_commit_da_versao_esperada_do_bridge():
    versao = expected_version()
    assert versao is not None
    for repo in (casos.REPO_BRIDGE, casos.REPO_NOVOMODELO):
        assert len(commit_esperado(repo, versao)) == 40


def test_fontes_sem_a_versao_falha(tmp_path):
    arquivo = tmp_path / "fontes.toml"
    arquivo.write_text('[novomodelo]\n"1.0.0" = "' + COMMIT + '"\n')
    assert commit_esperado("novomodelo", "1.0.0", arquivo) == COMMIT
    with pytest.raises(FalhaPreparo):
        commit_esperado("novomodelo", "2.0.0", arquivo)
    with pytest.raises(FalhaPreparo):
        commit_esperado("novomodelo-bridge", "1.0.0", arquivo)


def _termos_inventados() -> tuple[str, str]:
    return "zz" + "inventado" + "alfa", "zz" + "inventado" + "beta"


def _repo_com_executor(destino: Path) -> None:
    shutil.copytree(
        Path(__file__).parent,
        destino / "tests" / "e2e" / "executor",
        ignore=shutil.ignore_patterns("__pycache__", "fixtures"),
    )
    for comando in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", str(destino), *comando], check=True, capture_output=True)


def _checar(raiz: Path, termos: Path) -> subprocess.CompletedProcess:
    script = RAIZ / "scripts" / "ci" / "check_termos_proibidos.py"
    env = {**os.environ, "NOVOMODELO_TERMOS_INTERNOS": str(termos)}
    return subprocess.run(
        [sys.executable, str(script), "--raiz", str(raiz)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_nenhum_nome_interno_no_codigo(tmp_path):
    termos = tmp_path / "termos.txt"
    termos.write_text("\n".join(_termos_inventados()) + "\n", encoding="utf-8")
    raiz = tmp_path / "executor"
    _repo_com_executor(raiz)
    limpo = _checar(raiz, termos)
    assert limpo.returncode == 0, limpo.stdout + limpo.stderr
    (raiz / "tests" / "e2e" / "executor" / "plantado.py").write_text(
        f"x = '{_termos_inventados()[0]}'\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(raiz), "add", "-A"], check=True, capture_output=True)
    assert _checar(raiz, termos).returncode == 1
