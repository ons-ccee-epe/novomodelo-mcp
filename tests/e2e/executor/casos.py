"""Casos por nome lógico: os públicos preparados pela bateria e os grandes numa pasta externa."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from tests.e2e.config import Config
from tests.e2e.executor.container import (
    ENDURECIMENTO,
    PASTA_ESTUDOS,
    ComandoRecusado,
    Execucao,
    _montagem,
    encerrar_container,
    nome_container,
)
from tests.e2e.executor.imagens import FalhaPreparo, Rodar

PUBLICOS = frozenset(
    {"exemplo_1dtoy", "exemplo_1dtoy_rodado", "bridge_newave_mini", "bridge_decomp_mini"}
)
CASOS_GRANDES = frozenset({"caso_grande_newave", "caso_grande_rodado", "caso_grande_duas_rodadas"})
FONTES = Path(__file__).with_name("fontes.toml")
REPO_BRIDGE = "novomodelo-bridge"
REPO_NOVOMODELO = "novomodelo"
URL_PUBLICA = "https://github.com/ons-ccee-epe/{repo}"
DECKS = {"newave_mini": "bridge_newave_mini", "decomp_mini": "bridge_decomp_mini"}
PASTA_DECKS = "tests/decks"
PASTA_1DTOY = "examples/1dtoy"
TEMPO_GIT = 300
TEMPO_RODADA = 900
_VERSAO = re.compile(r"[0-9][0-9A-Za-z.+-]*")
_NOME_LOGICO = re.compile(r"[A-Za-z0-9_]+")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_AMBIENTE_GIT = {
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}
PREFIXO_GIT = ("git", "-c", "protocol.allow=never", "-c", "protocol.https.allow=always")


def pasta_preparados(cfg: Config) -> Path:
    return cfg.cache / "preparados"


def resolver(nome: str, cfg: Config, preparados: Path) -> Path | None:
    """O caminho do caso, ou `None` quando ele não está disponível.

    Raises:
        ValueError: o nome não é de um caso conhecido.
    """
    if not _NOME_LOGICO.fullmatch(nome):
        raise ValueError(f"caso desconhecido: {nome!r}")
    if nome in PUBLICOS:
        pasta = preparados / nome
    elif nome in CASOS_GRANDES:
        if cfg.casos is None:
            return None
        pasta = cfg.casos / nome
    else:
        raise ValueError(f"caso desconhecido: {nome}")
    return pasta if pasta.is_dir() else None


def commit_esperado(repo: str, versao: str, fontes: Path = FONTES) -> str:
    """O commit que a tag `v<versão>` do repositório público tem de apontar.

    Raises:
        FalhaPreparo: a versão não tem entrada no arquivo de fontes.
    """
    dados = tomllib.loads(fontes.read_text(encoding="utf-8"))
    commit = dados.get(repo, {}).get(versao)
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        raise FalhaPreparo(f"o commit da tag v{versao} de {repo} não está em fontes.toml")
    return commit


def _git(args: list[str], rodar: Rodar, *, cwd: Path | None = None) -> str:
    try:
        feito = rodar(
            [*PREFIXO_GIT, *args],
            capture_output=True,
            text=True,
            timeout=TEMPO_GIT,
            check=False,
            cwd=cwd,
            env={**os.environ, **_AMBIENTE_GIT},
        )
    except (OSError, subprocess.SubprocessError) as erro:
        raise FalhaPreparo(f"git {args[0]} falhou: {type(erro).__name__}") from None
    if feito.returncode != 0:
        raise FalhaPreparo(f"git {args[0]} falhou (código {feito.returncode})")
    return feito.stdout


def _clone_esparso(
    repo: str, versao: str, commit: str, pasta: str, cfg: Config, rodar: Rodar
) -> Path:
    """Clone raso da tag, só com `pasta`, no cache; o conteúdo só é usado com o commit certo.

    Raises:
        FalhaPreparo: versão ou commit mal formados, git com erro ou tag que não aponta
            para o commit esperado.
    """
    if not _VERSAO.fullmatch(versao) or not _COMMIT.fullmatch(commit):
        raise FalhaPreparo(f"versão ou commit inválido para {repo}")
    destino = cfg.cache / "fontes" / f"{repo}-v{versao}"
    if (destino / ".git").is_dir():
        try:
            intacto = (
                _git(["rev-parse", "HEAD"], rodar, cwd=destino).strip() == commit
                and not _git(
                    ["status", "--porcelain", "--untracked-files=all", "--ignored"],
                    rodar,
                    cwd=destino,
                ).strip()
            )
            if intacto:
                _git(["sparse-checkout", "set", "--", pasta], rodar, cwd=destino)
                return destino
        except FalhaPreparo:
            pass
    shutil.rmtree(destino, ignore_errors=True)
    destino.parent.mkdir(parents=True, exist_ok=True)
    url = URL_PUBLICA.format(repo=repo)
    clonar = ["clone", "--depth", "1", "--branch", f"v{versao}", "--filter=blob:none", "--sparse"]
    _git([*clonar, "--", url, str(destino)], rodar)
    obtido = _git(["rev-parse", "HEAD"], rodar, cwd=destino).strip()
    if obtido != commit:
        shutil.rmtree(destino, ignore_errors=True)
        raise FalhaPreparo(f"a tag v{versao} de {repo} não aponta para o commit esperado")
    _git(["sparse-checkout", "set", "--", pasta], rodar, cwd=destino)
    return destino


def _recusar_links_para_fora(origem: Path) -> None:
    raiz = origem.resolve()
    for caminho in origem.rglob("*"):
        try:
            # strict: a partir do Python 3.13, o resolve() não estrito devolve um laço de links sem erro.
            fora = caminho.is_symlink() and not caminho.resolve(strict=True).is_relative_to(raiz)
        except (OSError, RuntimeError):
            fora = True
        if fora:
            raise FalhaPreparo(
                f"link simbólico inválido ou para fora da pasta copiada: {caminho.name}"
            )


def _publicar(origem: Path, destino: Path) -> None:
    """Troca `destino` pela cópia de `origem`, sem deixar uma cópia pela metade.

    Raises:
        FalhaPreparo: a origem tem um link simbólico cujo alvo sai dela.
    """
    _recusar_links_para_fora(origem)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = Path(tempfile.mkdtemp(prefix=f".{destino.name}-", dir=destino.parent))
    try:
        copia = parcial / destino.name
        shutil.copytree(origem, copia, symlinks=True)
        shutil.rmtree(destino, ignore_errors=True)
        copia.rename(destino)
    finally:
        shutil.rmtree(parcial, ignore_errors=True)


def preparar_decks(
    versao_bridge: str, commit_esperado: str, cfg: Config, rodar: Rodar = subprocess.run
) -> Path:
    """Copia os decks mínimos do bridge na tag para `preparados/`; devolve essa pasta.

    Raises:
        FalhaPreparo: a tag não aponta para o commit esperado, git com erro ou deck
            ausente na tag.
    """
    clone = _clone_esparso(REPO_BRIDGE, versao_bridge, commit_esperado, PASTA_DECKS, cfg, rodar)
    for origem, nome in DECKS.items():
        fonte = clone / PASTA_DECKS / origem
        if not fonte.is_dir():
            raise FalhaPreparo(f"deck {origem} ausente na tag v{versao_bridge}")
        _publicar(fonte, pasta_preparados(cfg) / nome)
    return pasta_preparados(cfg)


def preparar_exemplo_1dtoy(
    versao: str, commit_esperado: str, cfg: Config, rodar: Rodar = subprocess.run
) -> Path:
    """Copia o `examples/1dtoy` do novomodelo na tag para `preparados/exemplo_1dtoy`.

    Raises:
        FalhaPreparo: a tag não aponta para o commit esperado, git com erro ou exemplo
            ausente na tag.
    """
    clone = _clone_esparso(REPO_NOVOMODELO, versao, commit_esperado, PASTA_1DTOY, cfg, rodar)
    fonte = clone / PASTA_1DTOY
    if not fonte.is_dir():
        raise FalhaPreparo(f"exemplo 1dtoy ausente na tag v{versao}")
    destino = pasta_preparados(cfg) / "exemplo_1dtoy"
    _publicar(fonte, destino)
    return destino


def preparar_1dtoy_rodado(imagem: str, cfg: Config, rodar: Rodar = subprocess.run) -> Path:
    """Roda `novomodelo run` na imagem sobre uma cópia do exemplo e grava o caso rodado.

    Raises:
        FalhaPreparo: exemplo ainda não preparado, rodada com erro ou sem saída.
    """
    preparados = pasta_preparados(cfg)
    exemplo = preparados / "exemplo_1dtoy"
    if not exemplo.is_dir():
        raise FalhaPreparo("exemplo_1dtoy não preparado")
    destino = preparados / "exemplo_1dtoy_rodado"
    trabalho = Path(tempfile.mkdtemp(prefix=".rodado-", dir=preparados))
    try:
        caso = trabalho / "exemplo_1dtoy_rodado"
        shutil.copytree(exemplo, caso, symlinks=True)
        shutil.rmtree(caso / "output", ignore_errors=True)
        dentro = f"{PASTA_ESTUDOS}/{caso.name}"
        nome = nome_container(
            Execucao(
                "preparo", caso.name, "claude", "sem-mcp", 0, "", None, False, TEMPO_RODADA, imagem
            ),
            "preparo",
        )
        try:
            montagem = _montagem("bind", str(caso), dentro, "relabel=private")
        except ComandoRecusado as erro:
            raise FalhaPreparo(str(erro)) from None
        cmd = [
            cfg.motor,
            "run",
            "--rm",
            f"--name={nome}",
            f"--memory={cfg.memoria}",
            f"--memory-swap={cfg.memoria}",
            *ENDURECIMENTO,
            "--network=none",
            *montagem,
            "-w",
            PASTA_ESTUDOS,
            imagem,
            "novomodelo",
            "run",
            dentro,
            "--quiet",
        ]
        try:
            feito = rodar(cmd, capture_output=True, timeout=TEMPO_RODADA, check=False)
        except (OSError, subprocess.SubprocessError) as erro:
            raise FalhaPreparo(f"a rodada do 1dtoy falhou: {type(erro).__name__}") from None
        finally:
            encerrar_container(cfg.motor, nome)
        if feito.returncode != 0:
            raise FalhaPreparo(f"a rodada do 1dtoy falhou (código {feito.returncode})")
        if not (caso / "output").is_dir():
            raise FalhaPreparo("a rodada do 1dtoy não gerou output")
        shutil.rmtree(destino, ignore_errors=True)
        caso.rename(destino)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)
    return destino


def preparar_publicos(versao: str, imagem: str, cfg: Config) -> list[str]:
    """Baixa e confere os casos públicos e gera o rodado; devolve os nomes preparados.

    Raises:
        FalhaPreparo: a versão não tem commit em `fontes.toml` ou qualquer etapa falhou.
    """
    preparar_decks(versao, commit_esperado(REPO_BRIDGE, versao), cfg)
    preparar_exemplo_1dtoy(versao, commit_esperado(REPO_NOVOMODELO, versao), cfg)
    preparar_1dtoy_rodado(imagem, cfg)
    return sorted(PUBLICOS)
