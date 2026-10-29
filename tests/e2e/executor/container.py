"""Uma execução de agente num container descartável: comando, leitura do stream e registro."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.e2e.config import Config
from tests.e2e.executor.eventos import Leitura, ler_claude, ler_kiro
from tests.e2e.executor.mascara import mascarar
from tests.e2e.resultado.armazenamento import caminho_execucao, gravar_registro
from tests.e2e.resultado.modelos import ChamadaTool, Estado, Registro

HOME_AGENTE = "/home/agente"
PASTA_ESTUDOS = "/estudos"
SEGREDO_CLAUDE = "novomodelo-bateria-claude-token"
MEMORIA = "6g"
LIMITE = re.compile(
    r"usage limit|rate.?limit|limit reached|hit your limit|quota|too many requests|"
    r"throttl|\b429\b|overloaded|credits? (exhausted|remaining: 0)",
    re.IGNORECASE,
)
_CONFIAR_KIRO = (
    "import json,pathlib;"
    "s=json.loads((pathlib.Path.home()/'.kiro'/'settings'/'mcp.json').read_text())"
    "['mcpServers']['novomodelo'];"
    "print(','.join('@novomodelo/'+t for t in s.get('autoApprove',[])))"
)
_TEMPO_LEITOR_ERRO = 30


@dataclass(frozen=True)
class Execucao:
    conjunto: str
    caso: str
    agente: Literal["claude", "kiro"]
    config: str
    repeticao: int
    pedido: str
    caso_origem: Path | None
    somente_leitura: bool
    timeout_s: int
    imagem: str


@dataclass(frozen=True)
class Saida:
    linhas: list[str]
    stderr: str
    codigo: int
    estourou: bool


def comando(e: Execucao, cfg: Config, trabalho: Path) -> list[str]:
    """Linha de comando do motor; o token só entra pelo segredo do motor, nunca por `-e`."""
    # Teto por container: uma tool que carregue dados demais morre sozinha, em vez de
    # esgotar a memória da máquina que roda a bateria.
    cmd = [cfg.motor, "run", "--rm", "-i", f"--memory={MEMORIA}", f"--memory-swap={MEMORIA}"]
    if Path(cfg.motor).name.startswith("podman"):
        cmd.append("--userns=keep-id")
    if e.agente == "claude":
        cmd += ["--secret", f"{SEGREDO_CLAUDE},type=env,target=CLAUDE_CODE_OAUTH_TOKEN"]
    else:
        cmd += ["-v", f"{cfg.volume_kiro}:{HOME_AGENTE}/.local/share/kiro-cli"]
    if e.caso_origem is not None:
        nome = e.caso_origem.name
        if e.somente_leitura:
            cmd += ["-v", f"{e.caso_origem}:{PASTA_ESTUDOS}/{nome}:ro,z"]
        else:
            cmd += ["-v", f"{trabalho / nome}:{PASTA_ESTUDOS}/{nome}:Z"]
    cmd += ["-w", PASTA_ESTUDOS, e.imagem]
    if e.agente == "claude":
        # Só o MCP que o `configurar` gravou: os conectores da conta do token não entram.
        cmd += [
            "claude",
            "-p",
            e.pedido,
            "--output-format",
            "stream-json",
            "--verbose",
            "--strict-mcp-config",
            "--mcp-config",
            f"{HOME_AGENTE}/mcp-do-configurar.json",
        ]
    else:
        # O kiro-cli ignora o `autoApprove` do mcp.json: as mesmas tools entram por nome no
        # --trust-tools, lidas do que o `configurar` gravou (paridade com o Claude).
        cmd += [
            "sh",
            "-c",
            "exec kiro-cli chat --output-format stream-json --trust-workspace "
            '--trust-tools="$(python3 -c "$1")" "$2"',
            "sh",
            _CONFIAR_KIRO,
            e.pedido,
        ]
    return cmd


def rodar_container(cmd: list[str], timeout_s: int) -> Saida:
    """Roda `cmd` e embrulha cada linha JSON do stdout com o instante de chegada.

    Raises:
        OSError: o executável de `cmd[0]` não existe.
    """
    t0 = time.monotonic()
    linhas: list[str] = []
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    estouro = threading.Event()

    def matar() -> None:
        estouro.set()
        proc.kill()

    # Vigia: um agente parado em silêncio não manda linha nenhuma, e o laço não acordaria.
    vigia = threading.Timer(timeout_s, matar)
    vigia.start()
    erros: list[str] = []
    leitor_erro = threading.Thread(
        target=lambda: erros.append(proc.stderr.read() if proc.stderr else "")
    )
    leitor_erro.start()
    try:
        for linha in proc.stdout or ():
            evento = None
            if linha.strip().startswith("{"):
                try:
                    evento = json.loads(linha)
                except ValueError:
                    evento = None
            linhas.append(
                json.dumps({"t": round(time.monotonic() - t0, 3), "evento": evento})
                if evento is not None
                else linha
            )
    finally:
        proc.wait()
        vigia.cancel()
        leitor_erro.join(timeout=_TEMPO_LEITOR_ERRO)
    return Saida(linhas, "".join(erros), proc.returncode, estouro.is_set())


def limite_atingido(linhas: list[str], erro: str) -> bool:
    """O agente parou por limite de uso, e não pelo caso."""
    if LIMITE.search(erro or ""):
        return True
    for linha in linhas[-5:]:
        try:
            ev = json.loads(linha).get("evento", {})
        except (ValueError, AttributeError):
            continue
        if not isinstance(ev, dict):
            continue
        if (
            ev.get("type") == "result"
            and ev.get("is_error")
            and LIMITE.search(str(ev.get("result", "")))
        ):
            return True
        if (
            ev.get("type") == "runFinished"
            and ev.get("data", {}).get("status") != "success"
            and LIMITE.search(json.dumps(ev.get("data", {})))
        ):
            return True
    return False


def _chamadas_mcp(leitura: Leitura) -> tuple[ChamadaTool, ...]:
    abertas: list[tuple[str, float]] = []
    fechadas: dict[int, tuple[bool, float]] = {}
    for ev in leitura.eventos:
        if not ev.do_mcp or ev.nome is None:
            continue
        if ev.tipo == "tool":
            abertas.append((ev.nome, ev.t))
        elif ev.tipo in ("resultado_tool", "negacao"):
            pendente = next(
                (i for i, (nome, _) in enumerate(abertas) if nome == ev.nome and i not in fechadas),
                None,
            )
            if pendente is not None:
                ok = ev.tipo == "resultado_tool" and not ev.erro
                fechadas[pendente] = (ok, ev.t)
    chamadas = []
    for i, (nome, t) in enumerate(abertas):
        if i in fechadas:
            ok, fim = fechadas[i]
            chamadas.append(ChamadaTool(nome, ok, round(max(fim - t, 0.0), 3)))
        else:
            chamadas.append(ChamadaTool(nome, None, None))
    return tuple(chamadas)


def _segredos(cfg: Config) -> tuple[str, ...]:
    try:
        valor = cfg.token_claude.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ()
    return (valor,) if valor else ()


def _motivo_de_infra(saida: Saida, leitura: Leitura) -> str | None:
    if saida.estourou:
        return "tempo esgotado: o container foi encerrado pelo vigia"
    if limite_atingido(saida.linhas, saida.stderr):
        return "limite de uso do agente atingido"
    if saida.codigo != 0 and not any(ev.tipo == "fim" for ev in leitura.eventos):
        return f"o container saiu com código {saida.codigo} sem evento de fim"
    return None


def executar(
    e: Execucao,
    cfg: Config,
    pasta_rodada: Path,
    avaliar: Callable[[Leitura], tuple[Estado, str]],
) -> Registro:
    """Roda uma execução e grava os logs mascarados e o registro; nunca levanta.

    Motor ausente, tempo esgotado, limite de uso, código diferente de zero sem evento de
    fim e uma exceção de `avaliar` viram `erro_infra` com o motivo.
    """
    t0 = time.monotonic()

    def registro(estado: Estado, motivo: str, tools: tuple[ChamadaTool, ...] = ()) -> Registro:
        return Registro(
            rodada=pasta_rodada.name,
            conjunto=e.conjunto,
            caso=e.caso,
            agente=e.agente,
            config=e.config,
            repeticao=e.repeticao,
            estado=estado,
            motivo=motivo,
            tools=tools,
            duracao_s=round(time.monotonic() - t0, 3),
        )

    try:
        destino = caminho_execucao(pasta_rodada, registro("erro_infra", ""))
        destino.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as erro:
        return registro("erro_infra", f"pasta da execução indisponível: {erro}")

    segredos = _segredos(cfg)
    saida = Saida([], "", -1, False)
    leitura = Leitura([])
    estado: Estado = "erro_infra"
    motivo = ""
    trabalho: Path | None = None
    try:
        trabalho = Path(tempfile.mkdtemp(prefix=".trabalho-", dir=pasta_rodada))
        if e.caso_origem is not None and not e.somente_leitura:
            shutil.copytree(e.caso_origem, trabalho / e.caso_origem.name)
        saida = rodar_container(comando(e, cfg, trabalho), e.timeout_s)
        leitura = (ler_claude if e.agente == "claude" else ler_kiro)(saida.linhas)
        motivo_infra = _motivo_de_infra(saida, leitura)
        if motivo_infra is not None:
            motivo = motivo_infra
        else:
            estado, motivo = avaliar(leitura)
    except FileNotFoundError as erro:
        motivo = f"motor de container ausente: {erro}"
    # Nunca levanta: qualquer falha da execução ou de `avaliar` vira `erro_infra` no registro,
    # em vez de derrubar a rodada inteira.
    except Exception as erro:
        motivo = f"falha na execução: {type(erro).__name__}: {erro}"
    finally:
        if trabalho is not None:
            shutil.rmtree(trabalho, ignore_errors=True)

    resposta = next(
        (ev.dados.get("resposta", "") for ev in reversed(leitura.eventos) if ev.tipo == "fim"), ""
    )
    final = registro(estado, mascarar(motivo, segredos), _chamadas_mcp(leitura))
    try:
        for nome, texto in (
            ("log.jsonl", "\n".join(saida.linhas) + "\n"),
            ("stderr.txt", saida.stderr),
            ("resposta.md", resposta),
        ):
            (destino / nome).write_text(mascarar(texto, segredos), encoding="utf-8")
        gravar_registro(pasta_rodada, final)
    except Exception as erro:
        return registro("erro_infra", f"falha ao gravar a execução: {type(erro).__name__}")
    return final
