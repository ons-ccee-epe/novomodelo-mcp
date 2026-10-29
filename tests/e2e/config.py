"""Configuração da bateria a partir do ambiente e verificação antes de uma rodada."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP = "novomodelo-mcp-bateria"
VOLUME_KIRO_PADRAO = "novomodelo-bateria-kiro"
TEMPO_MAXIMO_VOLUME = 15


ITENS = ("motor", "token_claude", "volume_kiro", "resultados", "cache", "casos", "cenarios_extra")


@dataclass(frozen=True)
class Config:
    motor: str
    resultados: Path
    casos: Path | None
    cenarios_extra: Path | None
    token_claude: Path
    volume_kiro: str
    cache: Path


@dataclass(frozen=True)
class Problema:
    item: str
    mensagem: str


def _valor(env: Mapping[str, str], nome: str) -> str | None:
    bruto = env.get(f"NOVOMODELO_BATERIA_{nome}")
    return bruto if bruto else None


def _caminho(bruto: str) -> Path:
    return Path(bruto).expanduser()


def carregar_config(
    env: Mapping[str, str],
    quem: Callable[[str], str | None] = shutil.which,
) -> Config:
    motor = _valor(env, "MOTOR") or ("podman" if quem("podman") else "docker")
    resultados = _valor(env, "RESULTADOS")
    casos = _valor(env, "CASOS")
    extra = _valor(env, "CENARIOS_EXTRA")
    token = _valor(env, "TOKEN_CLAUDE")
    return Config(
        motor=motor,
        resultados=(
            _caminho(resultados) if resultados else platformdirs.user_data_path(APP) / "resultados"
        ),
        casos=_caminho(casos) if casos else None,
        cenarios_extra=_caminho(extra) if extra else None,
        token_claude=(
            _caminho(token) if token else platformdirs.user_config_path(APP) / "token-claude"
        ),
        volume_kiro=_valor(env, "VOLUME_KIRO") or VOLUME_KIRO_PADRAO,
        cache=platformdirs.user_cache_path(APP),
    )


def volume_existe_no_motor(motor: str, nome: str) -> bool:
    try:
        done = subprocess.run(
            [motor, "volume", "inspect", "--", nome],
            capture_output=True,
            timeout=TEMPO_MAXIMO_VOLUME,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def _pasta_gravavel(pasta: Path) -> bool:
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=pasta):
            pass
    except OSError:
        return False
    return True


def _problema_do_token(token: Path) -> Problema | None:
    try:
        if not token.is_file():
            return Problema("token_claude", f"arquivo de token não encontrado: {token}")
        if sys.platform != "win32" and token.stat().st_mode & 0o777 != 0o600:
            return Problema(
                "token_claude",
                f"o arquivo de token precisa ter exatamente a permissão 600: {token}",
            )
    except OSError:
        return Problema("token_claude", f"arquivo de token inacessível: {token}")
    return None


def verificar(
    cfg: Config,
    quem: Callable[[str], str | None] = shutil.which,
    volume_existe: Callable[[str, str], bool] = volume_existe_no_motor,
) -> list[Problema]:
    """Devolve os problemas do ambiente; `Problema.item` é sempre um valor de `ITENS`."""
    problemas: list[Problema] = []
    motor_ok = quem(cfg.motor) is not None
    if not motor_ok:
        problemas.append(Problema("motor", f"motor de container '{cfg.motor}' fora do PATH"))
    problema_token = _problema_do_token(cfg.token_claude)
    if problema_token:
        problemas.append(problema_token)
    if not motor_ok:
        problemas.append(
            Problema("volume_kiro", "volume do Kiro não conferido: motor indisponível")
        )
    elif not volume_existe(cfg.motor, cfg.volume_kiro):
        problemas.append(
            Problema("volume_kiro", f"volume do login do Kiro '{cfg.volume_kiro}' não existe")
        )
    for item, pasta in (("resultados", cfg.resultados), ("cache", cfg.cache)):
        if not _pasta_gravavel(pasta):
            problemas.append(Problema(item, f"pasta não gravável: {pasta}"))
    for item, pasta in (("casos", cfg.casos), ("cenarios_extra", cfg.cenarios_extra)):
        if pasta is not None and not pasta.is_dir():
            problemas.append(Problema(item, f"pasta não encontrada: {pasta}"))
    return problemas


def avisos(cfg: Config, plataforma: str = sys.platform) -> list[str]:
    if plataforma == "win32":
        return [f"permissão do token não verificada neste sistema: {cfg.token_claude}"]
    return []
