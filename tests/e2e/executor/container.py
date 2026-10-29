"""Uma execução de agente num container descartável: comando, leitura do stream e registro."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tests.e2e.config import MOTIVO_MOTOR, Config, motor_suportado
from tests.e2e.executor.eventos import Evento, Leitura, ler_claude, ler_kiro
from tests.e2e.executor.mascara import mascarar
from tests.e2e.resultado.armazenamento import caminho_execucao, gravar_registro
from tests.e2e.resultado.modelos import ChamadaTool, Estado, Registro

HOME_AGENTE = "/home/agente"
PASTA_ESTUDOS = "/estudos"
SEGREDO_CLAUDE = "novomodelo-bateria-claude-token"
LIMITE_PIDS = 1024
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
_TEMPO_REMOCAO = 30
_MEMORIA_VALIDA = re.compile(r"[0-9]+[bkmgBKMG]?")
_FORA_DO_NOME = re.compile(r"[^A-Za-z0-9_.-]+")
_CAMINHO_ABSOLUTO = re.compile(r"(?<![\w.~:/-])(?:[A-Za-z]:[\\/]|\\\\|/)[^\s'\"]*")


class ComandoRecusado(ValueError):
    """A execução pede algo que o container não pode receber com segurança."""


class MotorAusente(OSError):
    """O executável do motor de container não foi encontrado."""


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


def nome_container(e: Execucao, rodada: str) -> str:
    base = "-".join(
        ("novomodelo-bateria", rodada, e.conjunto, e.caso, e.agente, e.config, str(e.repeticao))
    )
    return f"{_FORA_DO_NOME.sub('-', base)[:160]}-{uuid.uuid4().hex[:8]}"


def _conferir_caso_origem(origem: Path) -> None:
    # Montar a home (ou a raiz, que a contém) entrega ao agente as credenciais de quem roda:
    # a checagem vale depois de `resolve()`, que desfaz `..` e links simbólicos.
    real = origem.resolve()
    casa = Path.home().resolve()
    if real == Path(real.anchor) or real == casa or real in casa.parents:
        raise ComandoRecusado(
            "caso de origem recusado: é a raiz, a home de quem roda ou um ancestral dela"
        )


def _montagem(tipo: str, fonte: str, destino: str, *opcoes: str) -> list[str]:
    # Vírgula separa as opções do --mount: um caminho com vírgula injetaria opções novas.
    if "," in fonte or "," in destino:
        raise ComandoRecusado("caminho com vírgula não pode ser montado no container")
    return ["--mount", ",".join((f"type={tipo}", f"src={fonte}", f"dst={destino}", *opcoes))]


def comando(e: Execucao, cfg: Config, trabalho: Path, nome: str) -> list[str]:
    """Linha de comando do podman; o token só entra pelo secret do motor, nunca por `-e`.

    Raises:
        ComandoRecusado: motor que não é o podman, memória inválida, caso na raiz ou na
            home de quem roda, ou caminho que não pode ser montado.
    """
    if not motor_suportado(cfg.motor):
        raise ComandoRecusado(MOTIVO_MOTOR)
    if not _MEMORIA_VALIDA.fullmatch(cfg.memoria):
        raise ComandoRecusado(f"memória inválida: {cfg.memoria!r}")
    cmd = [
        cfg.motor,
        "run",
        "--rm",
        "-i",
        f"--name={nome}",
        f"--memory={cfg.memoria}",
        f"--memory-swap={cfg.memoria}",
        f"--pids-limit={LIMITE_PIDS}",
        "--security-opt=no-new-privileges",
        "--userns=keep-id",
    ]
    if e.agente == "claude":
        cmd += ["--secret", f"{SEGREDO_CLAUDE},type=env,target=CLAUDE_CODE_OAUTH_TOKEN"]
    else:
        cmd += _montagem("volume", cfg.volume_kiro, f"{HOME_AGENTE}/.local/share/kiro-cli")
    if e.caso_origem is not None:
        _conferir_caso_origem(e.caso_origem)
        destino = f"{PASTA_ESTUDOS}/{e.caso_origem.name}"
        if e.somente_leitura:
            cmd += _montagem("bind", str(e.caso_origem), destino, "readonly", "relabel=shared")
        else:
            cmd += _montagem("bind", str(trabalho / e.caso_origem.name), destino, "relabel=private")
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
        MotorAusente: o executável de `cmd[0]` não existe.
    """
    t0 = time.monotonic()
    linhas: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as erro:
        raise MotorAusente(Path(cmd[0]).name) from erro
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


def encerrar_container(motor: str, nome: str) -> None:
    """Remove o container pelo nome; matar só o cliente do motor deixaria o container vivo."""
    try:
        subprocess.run(
            [motor, "rm", "-f", nome], capture_output=True, timeout=_TEMPO_REMOCAO, check=False
        )
    except (OSError, subprocess.SubprocessError):
        pass


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


def _ok_do_envelope(ev: Evento) -> bool | None:
    if ev.tipo == "negacao" or ev.erro:
        return False
    try:
        envelope = json.loads(ev.dados.get("conteudo") or "")
    except ValueError:
        return None
    if isinstance(envelope, dict) and "status" in envelope:
        return envelope["status"] == "ok"
    return None


def _chamadas_mcp(leitura: Leitura) -> tuple[ChamadaTool, ...]:
    abertas: list[tuple[str, float]] = []
    fechadas: dict[int, tuple[bool | None, float]] = {}
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
                fechadas[pendente] = (_ok_do_envelope(ev), ev.t)
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


def _sem_caminhos(texto: str) -> str:
    return _CAMINHO_ABSOLUTO.sub("<caminho>", texto)


def _descrever(erro: BaseException) -> str:
    if isinstance(erro, OSError) and erro.strerror:
        return f"{type(erro).__name__}: {erro.strerror}"
    return f"{type(erro).__name__}: {erro}"


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

    Motor que não é o podman, caso indisponível ou recusado, motor ausente, tempo esgotado,
    limite de uso, código diferente de zero sem evento de fim e uma exceção de `avaliar`
    viram `erro_infra`; o motivo nunca leva caminho absoluto do host.
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
        return registro("erro_infra", _sem_caminhos(f"pasta da execução indisponível: {erro}"))

    segredos = _segredos(cfg)
    saida = Saida([], "", -1, False)
    leitura = Leitura([])
    estado: Estado = "erro_infra"
    motivo = ""
    trabalho: Path | None = None
    nome = nome_container(e, pasta_rodada.name)
    pode_estar_vivo = False
    try:
        if not motor_suportado(cfg.motor):
            motivo = MOTIVO_MOTOR
        elif e.caso_origem is not None and not e.caso_origem.exists():
            motivo = f"caso indisponível: {e.caso}"
        else:
            trabalho = Path(tempfile.mkdtemp(prefix=".trabalho-", dir=pasta_rodada))
            cmd = comando(e, cfg, trabalho, nome)
            if e.caso_origem is not None and not e.somente_leitura:
                shutil.copytree(e.caso_origem, trabalho / e.caso_origem.name)
            pode_estar_vivo = True
            saida = rodar_container(cmd, e.timeout_s)
            pode_estar_vivo = saida.estourou
            leitura = (ler_claude if e.agente == "claude" else ler_kiro)(saida.linhas)
            motivo_infra = _motivo_de_infra(saida, leitura)
            if motivo_infra is not None:
                motivo = motivo_infra
            else:
                estado, motivo = avaliar(leitura)
    except ComandoRecusado as erro:
        motivo = str(erro)
    except MotorAusente as erro:
        pode_estar_vivo = False
        motivo = f"motor de container ausente: {erro}"
    # Nunca levanta: qualquer falha da execução ou de `avaliar` vira `erro_infra` no registro,
    # em vez de derrubar a rodada inteira.
    except Exception as erro:
        motivo = f"falha na execução: {_descrever(erro)}"
    finally:
        if pode_estar_vivo:
            encerrar_container(cfg.motor, nome)
        if trabalho is not None:
            shutil.rmtree(trabalho, ignore_errors=True)

    resposta = next(
        (ev.dados.get("resposta", "") for ev in reversed(leitura.eventos) if ev.tipo == "fim"), ""
    )
    final = registro(estado, mascarar(_sem_caminhos(motivo), segredos), _chamadas_mcp(leitura))
    try:
        for arquivo, texto in (
            ("log.jsonl", "\n".join(saida.linhas) + "\n"),
            ("stderr.txt", saida.stderr),
            ("resposta.md", resposta),
        ):
            (destino / arquivo).write_text(mascarar(texto, segredos), encoding="utf-8")
        gravar_registro(pasta_rodada, final)
    except Exception as erro:
        return registro("erro_infra", f"falha ao gravar a execução: {type(erro).__name__}")
    return final
