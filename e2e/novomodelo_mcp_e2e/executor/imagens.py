"""Uma imagem por (agente, configuração do MCP), com as versões fixadas, e o secret do token."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from novomodelo_mcp.adapters.versions import expected_version
from novomodelo_mcp_e2e.config import MOTIVO_MOTOR, Config, motor_suportado
from novomodelo_mcp_e2e.executor.container import (
    ENDURECIMENTO,
    GID_AGENTE,
    HOME_AGENTE,
    PASTA_ESTUDOS,
    SEGREDO_CLAUDE,
    UID_AGENTE,
)

CONTAINERFILE = Path(__file__).with_name("Containerfile")
REPOSITORIO = "localhost/novomodelo-mcp-bateria"
CLAUDE_CODE_VERSAO = "2.1.310"
# O instalador oficial do Kiro só instala a última versão; com None a versão encontrada
# na imagem vai para o manifesto marcada como não fixada.
KIRO_CLI_VERSAO: str | None = None
NAO_FIXADA = " (não fixada)"
CLIENTES = {"claude": "claude-code", "kiro": "kiro"}
CHAVE_DO_AGENTE = {"claude": "claude-code", "kiro": "kiro-cli"}
DIST_WHEEL = "novomodelo_mcp"
_PIN_BRIDGE = re.compile(r"^Requires-Dist:\s*novomodelo[-_]bridge\s*==\s*([^;\s,]+)", re.MULTILINE)
TEMPO_LEITURA = 300
TEMPO_SEGREDO = 60
_FORA_DA_TAG = re.compile(r"[^A-Za-z0-9_.-]")

Rodar = Callable[..., subprocess.CompletedProcess]


class FalhaPreparo(RuntimeError):
    """A imagem ou o secret não ficaram prontos; a mensagem nunca leva o valor do token."""


@dataclass(frozen=True)
class ConfigMCP:
    nome: str
    wheel: Path | None


def ler_config_mcp(valor: str) -> ConfigMCP:
    """`"sem"` ou o caminho da wheel do MCP, cuja versão vem do nome do arquivo.

    Raises:
        ValueError: não é `sem` nem uma wheel do MCP existente.
    """
    if valor == "sem":
        return ConfigMCP("sem-mcp", None)
    wheel = Path(valor).expanduser()
    versao = versao_da_wheel(wheel)
    if not wheel.is_file():
        raise ValueError(f"wheel não encontrada: {wheel}")
    return ConfigMCP(f"mcp-{_FORA_DA_TAG.sub('_', versao)}", wheel.resolve())


def versao_da_wheel(wheel: Path) -> str:
    """A versão como o nome da wheel a escreve; `ConfigMCP.nome` traz só a forma da tag.

    Raises:
        ValueError: não é uma wheel do novomodelo-mcp ou a versão está vazia.
    """
    partes = wheel.name[: -len(".whl")].split("-") if wheel.suffix == ".whl" else []
    if len(partes) < 5 or partes[0] != DIST_WHEEL or not partes[1]:
        raise ValueError(f"não é 'sem' nem uma wheel do novomodelo-mcp: {wheel.name}")
    return partes[1]


def pin_do_bridge(wheel: Path) -> str:
    """O `novomodelo-bridge==` que a wheel exige, lido do METADATA dela.

    Raises:
        FalhaPreparo: wheel ilegível ou sem o pin do bridge.
    """
    try:
        with zipfile.ZipFile(wheel) as arquivo:
            nome = next(
                n
                for n in arquivo.namelist()
                if n.endswith(".dist-info/METADATA") and n.count("/") == 1
            )
            texto = arquivo.read(nome).decode("utf-8")
    except (OSError, StopIteration, UnicodeDecodeError, zipfile.BadZipFile):
        raise FalhaPreparo(f"METADATA ilegível na wheel {wheel.name}") from None
    achado = _PIN_BRIDGE.search(texto)
    if achado is None:
        raise FalhaPreparo(f"a wheel {wheel.name} não fixa o novomodelo-bridge")
    return achado.group(1)


def aviso_do_bridge(c: ConfigMCP) -> str | None:
    """Aviso quando o bridge da wheel não é o do pin deste checkout (as versões divergem).

    Raises:
        FalhaPreparo: wheel ilegível ou sem o pin do bridge.
    """
    if c.wheel is None:
        return None
    da_wheel = pin_do_bridge(c.wheel)
    do_checkout = expected_version()
    if do_checkout is not None and da_wheel != do_checkout:
        return (
            f"a wheel {c.wheel.name} fixa o novomodelo-bridge {da_wheel}; "
            f"o pin deste checkout é {do_checkout}"
        )
    return None


def tag_imagem(c: ConfigMCP, agente: str) -> str:
    if agente not in CLIENTES:
        raise ValueError(f"agente desconhecido: {agente}")
    return f"{REPOSITORIO}:{agente}-{c.nome}"


def versoes_fixadas() -> dict[str, str]:
    """Os `--build-arg` das versões; o novomodelo e o bridge seguem o pin do próprio MCP.

    Raises:
        FalhaPreparo: o pin do bridge não está nos metadados do novomodelo-mcp instalado.
    """
    novomodelo = expected_version()
    if novomodelo is None:
        raise FalhaPreparo("pin do novomodelo-bridge ausente nos metadados do novomodelo-mcp")
    return {
        "CLAUDE_CODE_VERSAO": CLAUDE_CODE_VERSAO,
        "KIRO_CLI_VERSAO": KIRO_CLI_VERSAO or "",
        "NOVOMODELO_VERSAO": novomodelo,
        "BRIDGE_VERSAO": novomodelo,
    }


def _exigir_podman(cfg: Config) -> None:
    if not motor_suportado(cfg.motor):
        raise FalhaPreparo(MOTIVO_MOTOR)


def construir(
    c: ConfigMCP, agente: str, cfg: Config, rodar: Rodar = subprocess.run
) -> dict[str, str]:
    """Constrói a imagem e devolve as versões lidas dela, com as chaves do manifesto.

    Raises:
        FalhaPreparo: motor que não é o podman, build com erro ou versões da imagem
            ausentes ou diferentes das fixadas.
    """
    _exigir_podman(cfg)
    tag = tag_imagem(c, agente)
    fixadas = versoes_fixadas()
    bridge = pin_do_bridge(c.wheel) if c.wheel is not None else fixadas["BRIDGE_VERSAO"]
    args = {
        **fixadas,
        "AGENTE": agente,
        "CLIENTE": CLIENTES[agente],
        "CONFIG": "mcp" if c.wheel is not None else "sem-mcp",
        "HOME_AGENTE": HOME_AGENTE,
        "PASTA_ESTUDOS": PASTA_ESTUDOS,
        "UID_AGENTE": str(UID_AGENTE),
        "GID_AGENTE": str(GID_AGENTE),
    }
    with tempfile.TemporaryDirectory(prefix="novomodelo-bateria-contexto-") as pasta:
        contexto = Path(pasta)
        (contexto / "wheel").mkdir()
        if c.wheel is not None:
            shutil.copy2(c.wheel, contexto / "wheel" / c.wheel.name)
        cmd = [cfg.motor, "build", "-f", str(CONTAINERFILE)]
        for nome, valor in args.items():
            cmd += ["--build-arg", f"{nome}={valor}"]
        cmd += ["-t", tag, str(contexto)]
        feito = rodar(cmd, check=False)
    if feito.returncode != 0:
        raise FalhaPreparo(f"build da imagem {tag} falhou (código {feito.returncode})")
    return _versoes_da_imagem(c, agente, cfg, tag, {**fixadas, "BRIDGE_VERSAO": bridge}, rodar)


def _versoes_da_imagem(
    c: ConfigMCP,
    agente: str,
    cfg: Config,
    tag: str,
    fixadas: dict[str, str],
    rodar: Rodar,
) -> dict[str, str]:
    # Com o mesmo --userns das execuções: o primeiro run rootless com keep-id prepara a
    # imagem (dezenas de segundos), e fora daqui esse tempo cairia na primeira execução.
    cmd = [cfg.motor, "run", "--rm", *ENDURECIMENTO, "--network=none", tag]
    cmd += ["cat", f"{HOME_AGENTE}/versoes.json"]
    try:
        feito = rodar(cmd, capture_output=True, text=True, timeout=TEMPO_LEITURA, check=False)
        lidas = json.loads(feito.stdout) if feito.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        lidas = None
    if not isinstance(lidas, dict):
        raise FalhaPreparo(f"versoes.json ilegível na imagem {tag}")
    chave = CHAVE_DO_AGENTE[agente]
    esperadas = {
        "novomodelo": fixadas["NOVOMODELO_VERSAO"],
        "novomodelo-bridge": fixadas["BRIDGE_VERSAO"],
    }
    if agente == "claude":
        esperadas[chave] = CLAUDE_CODE_VERSAO
    elif KIRO_CLI_VERSAO:
        esperadas[chave] = KIRO_CLI_VERSAO
    obrigatorias = ["novomodelo", "novomodelo-bridge", chave]
    if c.wheel is not None:
        obrigatorias.append("novomodelo-mcp")
        esperadas["novomodelo-mcp"] = versao_da_wheel(c.wheel)
    for nome in obrigatorias:
        if not isinstance(lidas.get(nome), str) or not lidas[nome]:
            raise FalhaPreparo(f"versão de {nome} ausente na imagem {tag}")
    for nome, valor in esperadas.items():
        if lidas[nome] != valor:
            raise FalhaPreparo(f"{nome} {lidas[nome]} na imagem {tag}; fixada: {valor}")
    versoes = {nome: lidas[nome] for nome in ("novomodelo", "novomodelo-bridge", chave)}
    if agente == "kiro" and not KIRO_CLI_VERSAO:
        versoes[chave] += NAO_FIXADA
    if c.wheel is not None:
        versoes[f"mcp:{c.nome}"] = lidas["novomodelo-mcp"]
    return versoes


def criar_segredo(cfg: Config, rodar: Rodar = subprocess.run) -> None:
    """Cria (ou troca) o secret do token do Claude no podman, que lê o próprio arquivo.

    O valor nunca passa pela linha de comando nem pela memória deste processo: o podman
    só aceita `-` com um pipe no stdin, e um pipe exigiria ler o token aqui. A mensagem de
    erro não leva a saída do motor, que poderia ecoá-lo.

    Raises:
        FalhaPreparo: motor que não é o podman, token inacessível ou recusa do motor.
    """
    _exigir_podman(cfg)
    if not cfg.token_claude.is_file():
        raise FalhaPreparo(f"arquivo de token não encontrado: {cfg.token_claude}")
    try:
        existe = rodar(
            [cfg.motor, "secret", "exists", SEGREDO_CLAUDE],
            capture_output=True,
            timeout=TEMPO_SEGREDO,
            check=False,
        )
        if existe.returncode not in (0, 1):
            raise FalhaPreparo(
                f"o motor não conferiu o secret {SEGREDO_CLAUDE} (código {existe.returncode})"
            )
        # O podman 4.9 recusa `--replace` quando o secret ainda não existe.
        troca = ["--replace"] if existe.returncode == 0 else []
        cmd = [cfg.motor, "secret", "create", *troca, SEGREDO_CLAUDE, str(cfg.token_claude)]
        feito = rodar(
            cmd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TEMPO_SEGREDO,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        raise FalhaPreparo(
            f"o motor falhou ao criar o secret {SEGREDO_CLAUDE}: {type(erro).__name__}"
        ) from None
    if feito.returncode != 0:
        raise FalhaPreparo(f"o motor recusou o secret {SEGREDO_CLAUDE} (código {feito.returncode})")
