"""Uma execução de agente num container descartável: comando, leitura do stream e registro."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path
from typing import Literal

from novomodelo_mcp_e2e.config import MOTIVO_MOTOR, Config, motor_suportado
from novomodelo_mcp_e2e.executor.eventos import Evento, Leitura, ler_claude, ler_kiro
from novomodelo_mcp_e2e.executor.mascara import mascarar
from novomodelo_mcp_e2e.resultado.armazenamento import caminho_execucao, gravar_registro
from novomodelo_mcp_e2e.resultado.modelos import Avaliacao, ChamadaTool, Estado, Metricas, Registro
from novomodelo_mcp_e2e.textos import sem_caminhos

HOME_AGENTE = "/home/agente"
PASTA_ESTUDOS = "/estudos"
SEGREDO_CLAUDE = "novomodelo-bateria-claude-token"
UID_AGENTE = 1000
GID_AGENTE = 1000
LIMITE_PIDS = 1024
# O usuário de quem roda vira o `agente` da imagem: com `keep-id` sem uid/gid o agente
# grava com um subuid no host, e o que ele cria na cópia do caso não sai no `rmtree`.
ENDURECIMENTO = (
    f"--pids-limit={LIMITE_PIDS}",
    "--security-opt=no-new-privileges",
    "--cap-drop=ALL",
    f"--userns=keep-id:uid={UID_AGENTE},gid={GID_AGENTE}",
)
LIMITE = re.compile(
    r"usage limit|rate.?limit|limit reached|hit your limit|quota|too many requests|"
    r"throttl|\b429\b|overloaded|credits? (exhausted|remaining: 0)",
    re.IGNORECASE,
)
_CONFIAR_KIRO = (
    "import json,pathlib,sys;"
    "s=json.loads((pathlib.Path.home()/'.kiro'/'settings'/'mcp.json').read_text())"
    "['mcpServers']['novomodelo'];"
    "t=s.get('autoApprove',[])+[x for x in sys.argv[1].split(',') if x];"
    "print(','.join('@novomodelo/'+n for n in t))"
)
PREFIXO_CLAUDE = "mcp__novomodelo__"
_NOME_TOOL = re.compile(r"[a-z_]+")
NUNCA_LIBERADAS = frozenset({"instalar_novomodelo"})
_TEMPO_LEITOR_ERRO = 30
_TEMPO_REMOCAO = 30
_MEMORIA_VALIDA = re.compile(r"[0-9]+[bkmgBKMG]?")
_FORA_DO_NOME = re.compile(r"[^A-Za-z0-9_.-]+")
_DESTINO_VALIDO = re.compile(r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")
SEM_OUTPUT = ("output", "output-*")


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
    montar_em: str | None = None
    sem_output: bool = False
    liberar: tuple[str, ...] = ()


@dataclass(frozen=True)
class Saida:
    linhas: list[str]
    stderr: str
    codigo: int
    estourou: bool


@dataclass(frozen=True)
class AnotacoesTool:
    """As dicas MCP de uma tool; `None` é dica que o servidor não declarou."""

    so_leitura: bool | None
    rede: bool | None


@cache
def tools_do_servidor() -> Mapping[str, AnotacoesTool]:
    """As tools que o servidor deste checkout registra, com as anotações de cada uma.

    Lidas do servidor montado em memória, sem subir processo: as anotações são a fonte
    única do que pede aprovação.
    """
    import anyio

    from novomodelo_mcp.server import build_server

    return {
        t.name: AnotacoesTool(
            so_leitura=t.annotations.readOnlyHint if t.annotations else None,
            rede=t.annotations.openWorldHint if t.annotations else None,
        )
        for t in anyio.run(build_server().list_tools)
    }


def conferir_liberadas(nomes: tuple[str, ...]) -> tuple[str, ...]:
    """Os nomes de `liberar`, se todos são tools do MCP que podem ser liberadas.

    Só tools do servidor novomodelo entram: um nome nativo (Bash, Write, WebFetch)
    ou um curinga liberaria o agente para fora do MCP. A recusa de rede e de tool sem
    anotação não depende do nome: uma tool nova sem classificação nunca é liberada.

    Raises:
        ComandoRecusado: nome fora do padrão, que o servidor não registra, de
            `NUNCA_LIBERADAS`, com acesso à rede (`openWorldHint`) ou sem
            `readOnlyHint`/`openWorldHint` declarados.
    """
    if not nomes:
        return ()
    registradas = tools_do_servidor()
    for nome in nomes:
        if not _NOME_TOOL.fullmatch(nome):
            raise ComandoRecusado(f"tool a liberar inválida: {nome!r}")
        if nome in NUNCA_LIBERADAS:
            raise ComandoRecusado(f"{nome} nunca é liberada: baixa e executa o instalador")
        anotacoes = registradas.get(nome)
        if anotacoes is None:
            raise ComandoRecusado(f"tool a liberar não registrada no servidor: {nome}")
        if anotacoes.so_leitura is None or anotacoes.rede is None:
            raise ComandoRecusado(f"tool a liberar sem anotação de leitura e rede: {nome}")
        if anotacoes.rede:
            raise ComandoRecusado(f"tool a liberar usa a rede: {nome}")
    return tuple(dict.fromkeys(nomes))


def nome_container(e: Execucao, rodada: str) -> str:
    base = "-".join(
        ("novomodelo-bateria", rodada, e.conjunto, e.caso, e.agente, e.config, str(e.repeticao))
    )
    return f"{_FORA_DO_NOME.sub('-', base)[:160]}-{uuid.uuid4().hex[:8]}"


def _homes() -> set[Path]:
    homes = {Path.home().resolve()}
    if sys.platform != "win32":
        import pwd

        homes.add(Path(pwd.getpwuid(os.getuid()).pw_dir).resolve())
    return homes


def _conferir_caso_origem(origem: Path) -> Path:
    """Devolve o caminho resolvido do caso; só ele é montado e copiado.

    Montar a home (ou a raiz, que a contém) entrega ao agente as credenciais de quem roda.
    `HOME` vem do ambiente, então a home da conta (`pwd`) também é protegida. Conferir
    um caminho e montar outro reabre a corrida entre a checagem e o uso.
    """
    real = origem.resolve()
    for casa in _homes():
        if real == Path(real.anchor) or real == casa or real in casa.parents:
            raise ComandoRecusado(
                "caso de origem recusado: é a raiz, a home de quem roda ou um ancestral dela"
            )
    return real


def _montagem(tipo: str, fonte: str, destino: str, *opcoes: str) -> list[str]:
    # Vírgula separa as opções do --mount: um caminho com vírgula injetaria opções novas.
    if "," in fonte or "," in destino:
        raise ComandoRecusado("caminho com vírgula não pode ser montado no container")
    return ["--mount", ",".join((f"type={tipo}", f"src={fonte}", f"dst={destino}", *opcoes))]


def destino_do_caso(e: Execucao) -> str:
    """Onde o caso fica no container: `<montar_em>/<nome da pasta>`, `/estudos` por padrão.

    Raises:
        ComandoRecusado: `montar_em` não é um caminho absoluto simples (sem `..`).
    """
    base = e.montar_em or PASTA_ESTUDOS
    if not _DESTINO_VALIDO.fullmatch(base) or ".." in base.split("/"):
        raise ComandoRecusado(f"destino do caso no container inválido: {base!r}")
    nome = e.caso_origem.name if e.caso_origem is not None else ""
    return f"{base}/{nome}"


def comando(e: Execucao, cfg: Config, trabalho: Path, nome: str) -> list[str]:
    """Linha de comando do podman; o token só entra pelo secret do motor, nunca por `-e`.

    Raises:
        ComandoRecusado: motor que não é o podman, memória inválida, caso na raiz ou na
            home de quem roda, destino do caso inválido ou caminho que não pode ser montado.
    """
    real = _conferir_caso_origem(e.caso_origem) if e.caso_origem is not None else None
    return _comando(e, cfg, trabalho, nome, real)


def _comando(
    e: Execucao, cfg: Config, trabalho: Path, nome: str, caso_real: Path | None
) -> list[str]:
    if not motor_suportado(cfg.motor):
        raise ComandoRecusado(MOTIVO_MOTOR)
    if not _MEMORIA_VALIDA.fullmatch(cfg.memoria):
        raise ComandoRecusado(f"memória inválida: {cfg.memoria!r}")
    liberadas = conferir_liberadas(e.liberar)
    cmd = [
        cfg.motor,
        "run",
        "--rm",
        "-i",
        f"--name={nome}",
        f"--memory={cfg.memoria}",
        f"--memory-swap={cfg.memoria}",
        *ENDURECIMENTO,
    ]
    if e.agente == "claude":
        cmd += ["--secret", f"{SEGREDO_CLAUDE},type=env,target=CLAUDE_CODE_OAUTH_TOKEN"]
    else:
        cmd += _montagem("volume", cfg.volume_kiro, f"{HOME_AGENTE}/.local/share/kiro-cli")
    if e.caso_origem is not None and caso_real is not None:
        destino = destino_do_caso(e)
        if e.somente_leitura:
            # Sem relabel: a pasta de casos é de quem roda e não pode ser reetiquetada.
            cmd += _montagem("bind", str(caso_real), destino, "readonly")
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
        if liberadas:
            cmd += ["--allowedTools", ",".join(PREFIXO_CLAUDE + n for n in liberadas)]
    else:
        # O kiro-cli ignora o `autoApprove` do mcp.json: as mesmas tools entram por nome no
        # --trust-tools, lidas do que o `configurar` gravou, mais as de `liberar`
        # (paridade com o Claude). Os nomes entram como argumento, nunca no script.
        cmd += [
            "sh",
            "-c",
            "exec kiro-cli chat --output-format stream-json --trust-workspace "
            '--trust-tools="$(python3 -c "$1" "$2")" "$3"',
            "sh",
            _CONFIAR_KIRO,
            ",".join(liberadas),
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


def encerrar_container(motor: str, nome: str) -> bool:
    """Remove o container pelo nome e diz se a remoção foi confirmada.

    Matar só o cliente do motor deixaria o container vivo; `--ignore` torna a remoção
    inofensiva quando o `--rm` já o removeu.
    """
    try:
        feito = subprocess.run(
            [motor, "rm", "-f", "--ignore", nome],
            capture_output=True,
            timeout=_TEMPO_REMOCAO,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return feito.returncode == 0


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


def _tokens(leitura: Leitura) -> tuple[int | None, int | None]:
    fim = next((ev for ev in reversed(leitura.eventos) if ev.tipo == "fim"), None)
    if fim is None:
        return None, None
    return fim.dados.get("tokens_entrada"), fim.dados.get("tokens_saida")


def _com_tokens(metricas: Metricas, leitura: Leitura, agente: str) -> Metricas:
    """Completa só os tokens ainda vazios; o Kiro não informa tokens e fica `None`."""
    if agente != "claude":
        return metricas
    entrada, saida = _tokens(leitura)
    return replace(
        metricas,
        tokens_entrada=metricas.tokens_entrada if metricas.tokens_entrada is not None else entrada,
        tokens_saida=metricas.tokens_saida if metricas.tokens_saida is not None else saida,
    )


def _segredos(cfg: Config) -> tuple[str, ...]:
    try:
        valor = cfg.token_claude.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ()
    return (valor,) if valor else ()


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
    avaliar: Callable[[Leitura], Avaliacao],
) -> Registro:
    """Roda uma execução e grava os logs mascarados e o registro; nunca levanta.

    Motor que não é o podman, caso indisponível ou recusado, motor ausente, tempo esgotado,
    limite de uso, código diferente de zero sem evento de fim e uma exceção de `avaliar`
    viram `erro_infra`; o motivo nunca leva caminho absoluto do host. Os tokens do stream
    do Claude entram nas métricas, também em `erro_infra`; o resto vem de `avaliar`.
    """
    t0 = time.monotonic()

    def registro(
        estado: Estado,
        motivo: str,
        tools: tuple[ChamadaTool, ...] = (),
        metricas: Metricas | None = None,
    ) -> Registro:
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
            metricas=metricas or Metricas(),
        )

    try:
        destino = caminho_execucao(pasta_rodada, registro("erro_infra", ""))
        destino.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as erro:
        return registro(
            "erro_infra",
            sem_caminhos(f"pasta da execução indisponível: {erro}", (pasta_rodada,)),
        )

    segredos = _segredos(cfg)
    saida = Saida([], "", -1, False)
    leitura = Leitura([])
    estado: Estado = "erro_infra"
    motivo = ""
    metricas = Metricas()
    trabalho: Path | None = None
    nome = nome_container(e, pasta_rodada.name)
    avisos: list[str] = []
    caso_real: Path | None = None
    popen_chamado = False
    try:
        if not motor_suportado(cfg.motor):
            motivo = MOTIVO_MOTOR
        elif (
            e.caso_origem is not None
            and not (caso_real := _conferir_caso_origem(e.caso_origem)).exists()
        ):
            motivo = f"caso indisponível: {e.caso}"
        else:
            trabalho = Path(tempfile.mkdtemp(prefix=".trabalho-", dir=pasta_rodada))
            cmd = _comando(e, cfg, trabalho, nome, caso_real)
            if e.caso_origem is not None and caso_real is not None and not e.somente_leitura:
                # Links copiados como links: seguir um link do caso copiaria arquivos do host
                # de fora dele para dentro do container.
                ignorar = shutil.ignore_patterns(*SEM_OUTPUT) if e.sem_output else None
                shutil.copytree(
                    caso_real, trabalho / e.caso_origem.name, symlinks=True, ignore=ignorar
                )
            popen_chamado = True
            saida = rodar_container(cmd, e.timeout_s)
            # O `avaliar` (e o juiz) só veem o stream mascarado: o agente pode ecoar o token.
            saida = replace(saida, linhas=[mascarar(linha, segredos) for linha in saida.linhas])
            leitura = (ler_claude if e.agente == "claude" else ler_kiro)(saida.linhas)
            motivo_infra = _motivo_de_infra(saida, leitura)
            if motivo_infra is not None:
                motivo = motivo_infra
            else:
                avaliacao = avaliar(leitura)
                estado, motivo, metricas = (
                    avaliacao.estado,
                    avaliacao.motivo,
                    avaliacao.metricas,
                )
    except ComandoRecusado as erro:
        motivo = str(erro)
    except MotorAusente as erro:
        popen_chamado = False
        motivo = f"motor de container ausente: {erro}"
    # Nunca levanta: qualquer falha da execução ou de `avaliar` vira `erro_infra` no registro,
    # em vez de derrubar a rodada inteira.
    except Exception as erro:
        motivo = f"falha na execução: {_descrever(erro)}"
    finally:
        if popen_chamado and not encerrar_container(cfg.motor, nome):
            avisos.append(f"container {nome} não confirmado como removido")
        if trabalho is not None:
            shutil.rmtree(trabalho, ignore_errors=True)

    resposta = next(
        (ev.dados.get("resposta", "") for ev in reversed(leitura.eventos) if ev.tipo == "fim"), ""
    )
    conhecidos = tuple(
        c for c in (e.caso_origem, caso_real, trabalho, pasta_rodada, cfg.casos) if c is not None
    )
    motivo = sem_caminhos(motivo, conhecidos)
    final = registro(
        estado,
        mascarar(motivo, segredos),
        _chamadas_mcp(leitura),
        _com_tokens(metricas, leitura, e.agente),
    )
    stderr = "\n".join([saida.stderr, *avisos]) if avisos else saida.stderr
    try:
        for arquivo, texto in (
            ("log.jsonl", "\n".join(saida.linhas) + "\n"),
            ("stderr.txt", stderr),
            ("resposta.md", resposta),
        ):
            (destino / arquivo).write_text(mascarar(texto, segredos), encoding="utf-8")
        gravar_registro(pasta_rodada, final)
    except Exception as erro:
        return registro("erro_infra", f"falha ao gravar a execução: {type(erro).__name__}")
    return final
