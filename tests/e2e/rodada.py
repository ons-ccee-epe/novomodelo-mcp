"""Rodada: a determinística, depois os conjuntos com agente, intercalados por configuração.

A pasta da rodada é `<resultados>/<rodada>`. Uma execução com `registro.json` não roda de
novo; a que bateu no limite de uso do agente ou do juiz tem a pasta apagada, para a
retomada refazê-la. No fim, o gitleaks varre a pasta inteira.
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tests.e2e.config import Config
from tests.e2e.conjuntos.tools.adaptador import avaliar_tools, carregar_casos, para_execucoes
from tests.e2e.conjuntos.usuario.cenario import Cenario, cenarios_da_rodada
from tests.e2e.conjuntos.usuario.juiz import (
    JUIZ_PADRAO,
    MOTIVO_LIMITE,
    Juiz,
    no_manifesto,
    prefixo_do_juiz,
)
from tests.e2e.conjuntos.usuario.pontuar import avaliar_usuario
from tests.e2e.executor.casos import CASOS_GRANDES, pasta_preparados, resolver
from tests.e2e.executor.container import (
    ENDURECIMENTO,
    Execucao,
    encerrar_container,
    executar,
    nome_container,
)
from tests.e2e.executor.imagens import (
    CHAVE_DO_AGENTE,
    ConfigMCP,
    FalhaPreparo,
    construir,
    tag_imagem,
)
from tests.e2e.queries.models import QueryTestCase
from tests.e2e.resultado.armazenamento import (
    NOME_MANIFESTO,
    NOME_REGISTRO,
    PADRAO_NOME,
    caminho_execucao,
    gravar_manifesto,
    gravar_registro,
    ler_manifesto,
)
from tests.e2e.resultado.modelos import Avaliacao, Conjunto, Estado, Manifesto, Registro

RAIZ = Path(__file__).resolve().parents[2]
TESTE_DETERMINISTICA = "tests/test_executaveis_reais.py"
AGENTE_DETERMINISTICA = "nenhum"
CONFIG_DETERMINISTICA = "checkout"
CONJUNTOS_COM_AGENTE: tuple[Conjunto, ...] = ("tools", "usuario")
DECKS_DETERMINISTICA = {"--newave-src": "bridge_newave_mini", "--decomp-src": "bridge_decomp_mini"}
TEMPO_DETERMINISTICA = 3600
TEMPO_LEITURA = 300
TEMPO_GITLEAKS = 900
ARQUIVO_LOG = "rodada.jsonl"
ARQUIVO_TRAVA = ".trava"
IDADE_MINIMA_TRAVA_ILEGIVEL_S = 5
ARQUIVO_BLOQUEIO = "BLOQUEADO-SEGREDO.txt"
MARCA_DETERMINISTICA = "concluida"
CONFIG_GITLEAKS = RAIZ / ".gitleaks.toml"
SUSPEITAS_DE_LIMITE = 3
TEMPO_FIM_THREADS = 120
ORIGEM_NAO_INFORMADA = "não informada"
NAO_USADO = "não usado nesta rodada"
MOTIVO_LIMITE_AGENTE = "limite de uso do agente atingido"
MOTIVO_LIMITE_JUIZ = f"falha na execução: LimiteDeUsoJuiz: {MOTIVO_LIMITE}"
MOTIVOS_LIMITE = frozenset({MOTIVO_LIMITE_AGENTE, MOTIVO_LIMITE_JUIZ})
CODIGO_DETERMINISTICA = 1
CODIGO_RECUSA = 2
CODIGO_SEGREDO = 3
CODIGO_LIMITE = 4
CODIGO_ORCAMENTO = 5
CODIGO_INTERROMPIDA = 130
CODIGOS_DE_SAIDA = {
    0: "rodada completa",
    CODIGO_DETERMINISTICA: (
        "determinística com falha, imagem não pronta ou execução sem registro gravado"
    ),
    CODIGO_RECUSA: "argumentos inválidos ou retomada recusada (outro plano, filtro ou commit)",
    CODIGO_SEGREDO: "segredo na pasta da rodada, ou varredura do gitleaks que não rodou",
    CODIGO_LIMITE: "limite de uso do agente ou do juiz, ou provável falso positivo do detector",
    CODIGO_ORCAMENTO: "orçamento de execuções ou de minutos estourado",
    CODIGO_INTERROMPIDA: "interrompida pelo Ctrl-C",
}
_FORA_DO_NOME = re.compile(r"[^A-Za-z0-9._-]+")
_LEITURA = (
    "import json; from novomodelo_mcp.client_config import read_only_tools; "
    "print(json.dumps(read_only_tools()))"
)
_PYTHON_DO_MCP = 'exec "$(uv tool dir)/novomodelo-mcp/bin/python" -c "$1"'


@dataclass(frozen=True)
class Orcamento:
    """Teto da rodada; zero é sem limite."""

    max_execucoes: int
    max_minutos: int


ORCAMENTO_PADRAO = Orcamento(2000, 240)


@dataclass(frozen=True)
class Planejada:
    """Uma execução da rodada e de onde ela veio; `pulado` traz o motivo sem executor."""

    execucao: Execucao
    fonte: Cenario | QueryTestCase
    pulado: str | None = None


@dataclass(frozen=True)
class Varredura:
    """O resultado do gitleaks: os arquivos com achado, ou o erro que impediu a varredura."""

    arquivos: tuple[str, ...] = ()
    erro: str | None = None


class RodadaInterrompida(RuntimeError):
    """A rodada parou antes do fim, ou terminou com achado de segredo; `codigo` é o de saída."""

    def __init__(self, codigo: int, motivo: str, pasta: Path | None = None) -> None:
        super().__init__(motivo)
        self.codigo = codigo
        self.pasta = pasta


def _nome(texto: str) -> str:
    return _FORA_DO_NOME.sub("-", texto).strip("-") or "teste"


def _registro_deterministica(
    rodada: str, caso: str, estado: Estado, motivo: str, duracao: float
) -> Registro:
    return Registro(
        rodada=rodada,
        conjunto="deterministica",
        caso=_nome(caso),
        agente=AGENTE_DETERMINISTICA,
        config=CONFIG_DETERMINISTICA,
        repeticao=1,
        estado=estado,
        motivo=motivo[:500],
        tools=(),
        duracao_s=round(duracao, 3),
    )


def registros_do_junit(junit: Path, rodada: str) -> list[Registro]:
    """Um registro por teste do JUnit XML, por `classname.name`: falha e erro viram `falhou`."""
    registros = []
    for caso in ET.parse(junit).getroot().iter("testcase"):
        estado: Estado = "passou"
        motivo = "passou"
        for filho in caso:
            if filho.tag in ("failure", "error"):
                estado, motivo = "falhou", filho.get("message") or filho.tag
                break
            if filho.tag == "skipped":
                estado, motivo = "pulado", filho.get("message") or "pulado"
        nome = ".".join(n for n in (caso.get("classname"), caso.get("name")) if n)
        registros.append(
            _registro_deterministica(rodada, nome, estado, motivo, float(caso.get("time") or 0))
        )
    return registros


def rodar_deterministica(
    pasta: Path, cfg: Config, rodar: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> list[Registro]:
    """Roda os testes com os executáveis reais e os decks mínimos do cache; nunca levanta."""
    destino = pasta / "deterministica"
    destino.mkdir(parents=True, exist_ok=True)
    junit = destino / "junit.xml"
    junit.unlink(missing_ok=True)
    cmd = [sys.executable, "-m", "pytest", TESTE_DETERMINISTICA, "--executaveis-reais", "-q"]
    cmd += ["-p", "no:cacheprovider", f"--junitxml={junit}"]
    preparados = pasta_preparados(cfg)
    for opcao, nome in DECKS_DETERMINISTICA.items():
        if (preparados / nome).is_dir():
            cmd += [opcao, str(preparados / nome)]
    t0 = time.monotonic()
    try:
        feito = rodar(
            cmd,
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=TEMPO_DETERMINISTICA,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        motivo = f"pytest não rodou: {type(erro).__name__}"
        return [_registro_deterministica(pasta.name, "pytest", "erro_infra", motivo, 0.0)]
    duracao = time.monotonic() - t0
    (destino / "saida.txt").write_text(f"{feito.stdout}\n{feito.stderr}", encoding="utf-8")
    try:
        registros = registros_do_junit(junit, pasta.name)
    except (OSError, ET.ParseError):
        registros = []
    if feito.returncode not in (0, 1) or not registros:
        motivo = f"pytest saiu com código {feito.returncode}"
        registros.append(
            _registro_deterministica(pasta.name, "pytest", "erro_infra", motivo, duracao)
        )
    return registros


def ler_leitura_mcp(
    c: ConfigMCP,
    agente: str,
    cfg: Config,
    rodar: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    encerrar: Callable[[str, str], bool] = encerrar_container,
) -> tuple[str, ...]:
    """As tools de leitura do MCP instalado na imagem, que o cliente roda sem aprovação.

    Raises:
        FalhaPreparo: a imagem não respondeu com a lista de tools.
    """
    if c.wheel is None:
        return ()
    tag = tag_imagem(c, agente)
    nome = f"novomodelo-bateria-leitura-{uuid.uuid4().hex[:8]}"
    cmd = [cfg.motor, "run", "--rm", f"--name={nome}", *ENDURECIMENTO, "--network=none", tag]
    cmd += ["sh", "-c", _PYTHON_DO_MCP, "sh", _LEITURA]
    try:
        feito = rodar(cmd, capture_output=True, text=True, timeout=TEMPO_LEITURA, check=False)
        linhas = feito.stdout.strip().splitlines() if feito.returncode == 0 else []
        nomes = json.loads(linhas[-1]) if linhas else None
    except (OSError, subprocess.SubprocessError, ValueError):
        nomes = None
    finally:
        encerrar(cfg.motor, nome)
    if not isinstance(nomes, list) or not all(isinstance(n, str) for n in nomes):
        raise FalhaPreparo(f"tools de leitura do MCP ilegíveis na imagem {tag}")
    return tuple(nomes)


def varrer_segredos(pasta: Path, config: Path = CONFIG_GITLEAKS) -> Varredura:
    """Roda `gitleaks dir --redact` com a config do repo e devolve só os arquivos com achado.

    A config é passada explícita e o `cwd` é uma pasta vazia: sem isso o gitleaks usa só as
    regras padrão, que não reconhecem o token OAuth do Claude (`sk-ant-oat01-`).
    """
    exe = shutil.which("gitleaks")
    if exe is None:
        return Varredura(erro="gitleaks fora do PATH: a pasta da rodada não foi varrida")
    if not config.is_file():
        return Varredura(erro="config do gitleaks ausente: a pasta da rodada não foi varrida")
    with tempfile.TemporaryDirectory(prefix="novomodelo-bateria-gitleaks-") as tmp:
        relatorio = Path(tmp) / "achados.json"
        cmd = [exe, "dir", "--redact", "--no-banner", "--config", str(config)]
        cmd += ["--report-format", "json", "--report-path", str(relatorio), "--exit-code", "1"]
        cmd.append(str(pasta.resolve()))
        try:
            feito = subprocess.run(
                cmd, cwd=tmp, capture_output=True, timeout=TEMPO_GITLEAKS, check=False
            )
        except (OSError, subprocess.SubprocessError) as erro:
            return Varredura(erro=f"gitleaks falhou: {type(erro).__name__}")
        if feito.returncode not in (0, 1):
            return Varredura(erro=f"gitleaks saiu com código {feito.returncode}")
        try:
            achados = json.loads(relatorio.read_text(encoding="utf-8")) if feito.returncode else []
        except (OSError, ValueError):
            return Varredura(erro="relatório do gitleaks ilegível")
    arquivos = set()
    for achado in achados:
        arquivo = Path(str(achado.get("File", "")))
        try:
            arquivos.add(arquivo.resolve().relative_to(pasta.resolve()).as_posix())
        except ValueError:
            arquivos.add(arquivo.name)
    if feito.returncode and not arquivos:
        arquivos.add("(arquivo não informado pelo gitleaks)")
    return Varredura(tuple(sorted(arquivos)))


def encerrar_em_voo(cfg: Config, prefixos: Sequence[str]) -> list[str]:
    """Remove os containers da bateria cujo nome é `<prefixo>-…`; devolve os nomes.

    O separador entra na comparação: sem ele, o prefixo da repetição 1 casaria a 10.
    """
    if not prefixos:
        return []
    try:
        feito = subprocess.run(
            [
                cfg.motor,
                "ps",
                "-a",
                "--format",
                "{{.Names}}",
                "--filter",
                "name=novomodelo-bateria",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    nomes = [n for n in feito.stdout.split() if n.startswith(tuple(f"{p}-" for p in prefixos))]
    for nome in nomes:
        encerrar_container(cfg.motor, nome)
    return nomes


def prefixo_do_container(e: Execucao, rodada: str) -> str:
    """O nome que o executor dá ao container de `e`, sem o sufixo aleatório."""
    return nome_container(e, rodada).rsplit("-", 1)[0]


def commit_da_bateria() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.strip()
        sujo = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "desconhecido"
    return f"{commit}+alterações locais" if sujo else commit


def sha256(arquivo: Path) -> str:
    h = hashlib.sha256()
    with arquivo.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


@dataclass(frozen=True)
class Dependencias:
    """O que a rodada chama fora deste processo; os testes trocam por falsos."""

    executar: Callable[..., Registro] = executar
    construir: Callable[[ConfigMCP, str, Config], dict[str, str]] = construir
    leitura_mcp: Callable[[ConfigMCP, str, Config], tuple[str, ...]] = ler_leitura_mcp
    deterministica: Callable[[Path, Config], list[Registro]] = rodar_deterministica
    varrer: Callable[[Path], Varredura] = varrer_segredos
    commit: Callable[[], str] = commit_da_bateria
    relogio: Callable[[], float] = time.monotonic
    esperar: Callable[[float], None] = time.sleep
    encerrar_em_voo: Callable[[Config, Sequence[str]], list[str]] = encerrar_em_voo
    pid_vivo: Callable[[int], bool] = lambda pid: pid_vivo(pid)


def pid_vivo(pid: int) -> bool:
    """Se há processo com esse PID; `os.kill(pid, 0)` no Windows mandaria Ctrl-C, então lá é a API."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        codigo = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo))
        kernel32.CloseHandle(handle)
        return bool(ok) and codigo.value == 259
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_da_trava(trava: Path) -> int | None:
    try:
        return int(trava.read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None


def trava_viva(pasta: Path, vivo: Callable[[int], bool] = pid_vivo) -> int | None:
    """O PID de quem segura a trava da pasta, se ele ainda existe; `None` sem trava ou velha."""
    trava = pasta / ARQUIVO_TRAVA
    pid = _pid_da_trava(trava)
    if pid is None:
        try:
            recente = time.time() - trava.stat().st_mtime < IDADE_MINIMA_TRAVA_ILEGIVEL_S
        except OSError:
            return None
        return 0 if recente else None
    return pid if vivo(pid) else None


def _adquirir_trava(pasta: Path, rodada: str, vivo: Callable[[int], bool]) -> int | None:
    """Cria a trava exclusiva da rodada; devolve o PID da trava velha que substituiu, se houve.

    A criação é `O_CREAT|O_EXCL`: duas rodadas com o mesmo nome nunca passam juntas.

    Raises:
        RodadaInterrompida: `CODIGO_RECUSA`, com a trava segurada por um processo vivo.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    trava = pasta / ARQUIVO_TRAVA
    velha: int | None = None
    for _ in range(3):
        try:
            fd = os.open(trava, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            dono = trava_viva(pasta, vivo)
            if dono is not None:
                quem = f"PID {dono}" if dono else "outro processo"
                raise RodadaInterrompida(
                    CODIGO_RECUSA, f"a rodada {rodada} já está em andamento ({quem})"
                ) from None
            velha = _pid_da_trava(trava) or velha
            trava.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{os.getpid()} {datetime.now(UTC).isoformat(timespec='seconds')}\n")
        return velha
    raise RodadaInterrompida(
        CODIGO_RECUSA, f"a rodada {rodada} está sendo iniciada por outro processo"
    )


def _config_do_juiz(configs: Sequence[ConfigMCP]) -> ConfigMCP:
    return configs[0]


def _execucao_usuario(
    c: Cenario, config: ConfigMCP, agente: str, rep: int, cfg: Config
) -> Planejada:
    origem = None
    pulado = None
    if c.caso is not None:
        origem = resolver(c.caso, cfg, pasta_preparados(cfg))
        if origem is None and c.caso in CASOS_GRANDES:
            pulado = f"caso ausente: {c.caso}"
        elif origem is None:
            origem = pasta_preparados(cfg) / c.caso
    e = Execucao(
        conjunto="usuario",
        caso=c.id,
        agente=agente,
        config=config.nome,
        repeticao=rep,
        pedido=c.pedido,
        caso_origem=origem,
        somente_leitura=c.somente_leitura,
        timeout_s=c.timeout_s,
        imagem=tag_imagem(config, agente),
        montar_em=c.montar_em,
        sem_output=c.sem_output,
    )
    return Planejada(e, c, pulado)


def planejar(
    configs: Sequence[ConfigMCP],
    conjuntos: Sequence[Conjunto],
    agentes: Sequence[str],
    repeticoes: int,
    cfg: Config,
    filtro: str | None = None,
) -> list[Planejada]:
    """As execuções com agente, na ordem repetição → conjunto → caso → configuração → agente.

    Com a configuração no laço de dentro, uma rodada parada no meio deixa as configurações
    com o mesmo número de execuções de cada caso. O conjunto de tools só roda com MCP.
    """
    ordem_config = {c.nome: i for i, c in enumerate(configs)}
    ordem_agente = {a: i for i, a in enumerate(agentes)}
    planejadas: list[Planejada] = []
    if "tools" in conjuntos:
        padroes = [p.strip() for p in (filtro or "").split(",") if p.strip()]
        casos = [
            c
            for c in carregar_casos()
            if not padroes or any(fnmatch.fnmatch(c.id, p) for p in padroes)
        ]
        por_id = {c.id: c for c in casos}
        com_mcp = [c for c in configs if c.wheel is not None]
        for e in para_execucoes(
            casos, cfg, agentes=agentes, configs=com_mcp, repeticoes=repeticoes
        ):
            planejadas.append(Planejada(e, por_id[e.caso]))
    if "usuario" in conjuntos:
        cenarios, _ = cenarios_da_rodada(cfg, filtro)
        for c in cenarios:
            for config in configs:
                for agente in agentes:
                    for rep in range(1, repeticoes + 1):
                        planejadas.append(_execucao_usuario(c, config, agente, rep, cfg))
    ordem_conjunto = {c: i for i, c in enumerate(CONJUNTOS_COM_AGENTE)}
    return sorted(
        planejadas,
        key=lambda p: (
            p.execucao.repeticao,
            ordem_conjunto[p.execucao.conjunto],
            p.execucao.caso,
            ordem_config[p.execucao.config],
            ordem_agente[p.execucao.agente],
        ),
    )


Chave = tuple[str, str, str, str, int]


def chaves_planejadas(m: Manifesto, cfg: Config) -> set[Chave]:
    """As execuções com agente que o plano do manifesto prevê: conjunto, caso, agente, config e
    repetição, com o filtro dele; um caso pulado também tem registro e entra no plano."""
    configs = [
        ConfigMCP(nome, Path(m.wheels[nome]["arquivo"]) if nome in m.wheels else None)
        for nome in m.configs
    ]
    conjuntos = [c for c in m.conjuntos if c in CONJUNTOS_COM_AGENTE]
    return {
        (e.conjunto, e.caso, e.agente, e.config, e.repeticao)
        for e in (
            p.execucao for p in planejar(configs, conjuntos, m.agentes, m.repeticoes, cfg, m.filtro)
        )
    }


def ultimo_fim(pasta: Path) -> tuple[int, str] | None:
    """O código e o motivo do último evento `fim` do log da rodada; `None` sem nenhum."""
    try:
        linhas = (pasta / ARQUIVO_LOG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for linha in reversed(linhas):
        try:
            evento = json.loads(linha)
        except ValueError:
            continue
        if isinstance(evento, dict) and evento.get("evento") == "fim":
            codigo = evento.get("codigo")
            return (codigo if isinstance(codigo, int) else -1), str(evento.get("motivo", ""))
    return None


def _imagens_da_rodada(
    configs: Sequence[ConfigMCP], agentes: Sequence[str], com_juiz: bool
) -> list[tuple[ConfigMCP, str]]:
    pares = [(c, a) for c in configs for a in agentes]
    juiz = (_config_do_juiz(configs), "claude")
    if com_juiz and juiz not in pares:
        pares.append(juiz)
    return pares


def _versoes(
    imagens: Mapping[str, dict[str, str]], agentes: Sequence[str], juiz: Juiz, imagem_juiz: str
) -> dict[str, str]:
    juntas: dict[str, set[str]] = {}
    for versoes in imagens.values():
        for nome, valor in versoes.items():
            juntas.setdefault(nome, set()).add(valor)
    planas = {nome: ", ".join(sorted(valores)) for nome, valores in juntas.items()}
    for agente, chave in CHAVE_DO_AGENTE.items():
        if agente not in agentes and chave not in planas:
            planas[chave] = NAO_USADO
    do_juiz = no_manifesto(juiz)
    planas["juiz-modelo"] = do_juiz["juiz_modelo"]
    planas["juiz-temperatura"] = do_juiz["juiz_temperatura"]
    planas["juiz-imagem"] = imagem_juiz
    return planas


def _wheels(configs: Sequence[ConfigMCP], origens: Mapping[str, str]) -> dict[str, dict[str, str]]:
    return {
        c.nome: {
            "arquivo": c.wheel.name,
            "sha256": sha256(c.wheel),
            "origem": origens.get(c.nome, ORIGEM_NAO_INFORMADA),
        }
        for c in configs
        if c.wheel is not None
    }


def _diferenca(gravado: Manifesto, novo: Manifesto) -> str | None:
    """O que impede retomar `gravado` com o plano `novo`, ou `None` se é a mesma rodada."""
    if gravado.filtro != novo.filtro:
        return f"filtro {gravado.filtro!r} gravado, {novo.filtro!r} pedido"
    if gravado.commit_bateria != novo.commit_bateria:
        return f"bateria no commit {gravado.commit_bateria}, agora {novo.commit_bateria}"

    def chave(m: Manifesto) -> tuple:
        return (
            m.configs,
            m.conjuntos,
            m.agentes,
            m.repeticoes,
            m.versoes,
            m.imagens,
            {nome: w["sha256"] for nome, w in m.wheels.items()},
        )

    if chave(gravado) != chave(novo):
        return "outro plano (configurações, conjuntos, agentes, repetições) ou outras versões"
    return None


class _Log:
    def __init__(self, pasta: Path) -> None:
        self._arquivo = pasta / ARQUIVO_LOG
        self._trava = threading.Lock()

    def __call__(self, evento: str, **dados: object) -> None:
        linha = {"t": datetime.now(UTC).isoformat(timespec="seconds"), "evento": evento, **dados}
        with self._trava, self._arquivo.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def _pasta_da_execucao(pasta: Path, e: Execucao) -> Path:
    marca = Registro(
        rodada=pasta.name,
        conjunto=e.conjunto,
        caso=e.caso,
        agente=e.agente,
        config=e.config,
        repeticao=e.repeticao,
        estado="erro_infra",
        motivo="",
        tools=(),
        duracao_s=0.0,
    )
    return caminho_execucao(pasta, marca)


def _de_limite(estado: str | None, motivo: str | None) -> bool:
    return estado == "erro_infra" and motivo in MOTIVOS_LIMITE


def _feita(pasta: Path, e: Execucao) -> bool:
    """Já tem resultado; um registro de limite de uso (sobra de uma parada) não conta."""
    arquivo = _pasta_da_execucao(pasta, e) / NOME_REGISTRO
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        estado, motivo = dados.get("estado"), dados.get("motivo")
    except (OSError, ValueError, AttributeError):
        return False
    if _de_limite(estado, motivo):
        shutil.rmtree(arquivo.parent, ignore_errors=True)
        return False
    return True


@dataclass
class _Controle:
    t0: float
    iniciadas: int = 0
    esperado_s: float = 0.0
    parada: str | None = None
    suspeitas: dict[str, int] = field(default_factory=dict)
    limites_na_passada: list[str] = field(default_factory=list)
    concluidas_na_passada: int = 0
    em_voo: dict[str, Execucao] = field(default_factory=dict)
    pasta: Path | None = None
    trava_velha: int | None = None
    erro: BaseException | None = None
    trava: threading.Lock = field(default_factory=threading.Lock)


def _estourou(ctl: _Controle, orcamento: Orcamento, agora: float) -> bool:
    """A espera do limite de uso não conta no tempo; a execução refeita conta uma vez só."""
    if orcamento.max_execucoes and ctl.iniciadas >= orcamento.max_execucoes:
        return True
    decorrido = agora - ctl.t0 - ctl.esperado_s
    return bool(orcamento.max_minutos and decorrido >= orcamento.max_minutos * 60)


def rodar(
    rodada: str | None,
    configs: Sequence[ConfigMCP],
    conjuntos: Sequence[Conjunto],
    agentes: Sequence[str],
    repeticoes: int,
    cfg: Config,
    orcamento: Orcamento = ORCAMENTO_PADRAO,
    paralelo_por_agente: int = 3,
    *,
    filtro: str | None = None,
    completa: bool = False,
    origens: Mapping[str, str] | None = None,
    esperar_limite_min: int | None = None,
    juiz: Juiz = JUIZ_PADRAO,
    dep: Dependencias | None = None,
) -> Path:
    """Cria ou retoma `<resultados>/<rodada>` e devolve a pasta da rodada completa.

    Raises:
        RodadaInterrompida: com `codigo` de `CODIGOS_DE_SAIDA`; a pasta, quando existe,
            já tem o que foi feito e foi varrida pelo gitleaks.
    """
    dep = dep or Dependencias()
    origens = origens or {}
    rodada = rodada or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not re.search(PADRAO_NOME, rodada):
        raise RodadaInterrompida(CODIGO_RECUSA, f"nome de rodada inválido: {rodada!r}")
    if not configs:
        raise RodadaInterrompida(CODIGO_RECUSA, "nenhuma configuração do MCP")
    pasta_da_rodada = cfg.resultados / rodada
    velha = _adquirir_trava(pasta_da_rodada, rodada, dep.pid_vivo)
    try:
        return _rodar_com_trava(
            rodada,
            velha,
            configs,
            conjuntos,
            agentes,
            repeticoes,
            cfg,
            orcamento,
            paralelo_por_agente,
            filtro,
            completa,
            origens,
            esperar_limite_min,
            juiz,
            dep,
        )
    finally:
        (pasta_da_rodada / ARQUIVO_TRAVA).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            pasta_da_rodada.rmdir()


def _rodar_com_trava(
    rodada: str,
    velha: int | None,
    configs: Sequence[ConfigMCP],
    conjuntos: Sequence[Conjunto],
    agentes: Sequence[str],
    repeticoes: int,
    cfg: Config,
    orcamento: Orcamento,
    paralelo_por_agente: int,
    filtro: str | None,
    completa: bool,
    origens: Mapping[str, str],
    esperar_limite_min: int | None,
    juiz: Juiz,
    dep: Dependencias,
) -> Path:
    ctl = _Controle(t0=dep.relogio())
    ctl.trava_velha = velha
    try:
        pasta, log, codigo, motivo = _preparar_e_rodar(
            rodada,
            configs,
            conjuntos,
            agentes,
            repeticoes,
            cfg,
            orcamento,
            paralelo_por_agente,
            filtro,
            completa,
            origens,
            esperar_limite_min,
            juiz,
            dep,
            ctl,
        )
    except KeyboardInterrupt:
        motivo = "rodada interrompida (Ctrl-C); retome com o mesmo --rodada"
        if ctl.pasta is None:
            raise RodadaInterrompida(CODIGO_INTERROMPIDA, motivo) from None
        with _sem_ctrl_c():
            log = _Log(ctl.pasta)
            log("interrompida", em_voo=[])
            _fechar(ctl.pasta, log, dep, CODIGO_INTERROMPIDA, motivo)
        raise RodadaInterrompida(CODIGO_INTERROMPIDA, motivo, ctl.pasta) from None
    except BaseException:
        if ctl.pasta is not None:
            with _sem_ctrl_c():
                _bloquear_se_achar(ctl.pasta, _Log(ctl.pasta), dep)
        raise
    with _sem_ctrl_c():
        _fechar(pasta, log, dep, codigo, motivo)
    if codigo:
        raise RodadaInterrompida(codigo, motivo, pasta)
    return pasta


def gravar_bloqueio(pasta: Path, varredura: Varredura) -> bool:
    """Achado ou varredura que não rodou grava `ARQUIVO_BLOQUEIO`; devolve se bloqueou."""
    if not (varredura.erro or varredura.arquivos):
        return False
    linhas = [varredura.erro] if varredura.erro else []
    linhas += [f"segredo encontrado em: {a}" for a in varredura.arquivos]
    (pasta / ARQUIVO_BLOQUEIO).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return True


def _bloquear_se_achar(pasta: Path, log: _Log, dep: Dependencias) -> bool:
    varredura = dep.varrer(pasta)
    if not gravar_bloqueio(pasta, varredura):
        return False
    log("segredo", arquivos=list(varredura.arquivos), erro=varredura.erro)
    return True


def _fechar(pasta: Path, log: _Log, dep: Dependencias, codigo: int, motivo: str) -> None:
    """Varre e registra o fim.

    Raises:
        RodadaInterrompida: `CODIGO_SEGREDO`, quando a varredura bloqueia.
    """
    if _bloquear_se_achar(pasta, log, dep):
        raise RodadaInterrompida(
            CODIGO_SEGREDO, f"varredura de segredos bloqueou a rodada: {ARQUIVO_BLOQUEIO}", pasta
        )
    log("fim", codigo=codigo, motivo=motivo)


def _preparar_e_rodar(
    rodada: str,
    configs: Sequence[ConfigMCP],
    conjuntos: Sequence[Conjunto],
    agentes: Sequence[str],
    repeticoes: int,
    cfg: Config,
    orcamento: Orcamento,
    paralelo_por_agente: int,
    filtro: str | None,
    completa: bool,
    origens: Mapping[str, str],
    esperar_limite_min: int | None,
    juiz: Juiz,
    dep: Dependencias,
    ctl: _Controle,
) -> tuple[Path, _Log, int, str]:
    com_juiz = "usuario" in conjuntos
    imagem_juiz = tag_imagem(_config_do_juiz(configs), "claude")
    imagens: dict[str, dict[str, str]] = {}
    leituras: dict[str, tuple[str, ...]] = {}
    try:
        for c, agente in _imagens_da_rodada(configs, agentes, com_juiz):
            imagens[tag_imagem(c, agente)] = dep.construir(c, agente, cfg)
        for c in configs:
            leituras[c.nome] = dep.leitura_mcp(c, agentes[0], cfg)
    except FalhaPreparo as erro:
        raise RodadaInterrompida(
            CODIGO_DETERMINISTICA, f"imagem não ficou pronta: {erro}"
        ) from None
    planejadas = planejar(configs, conjuntos, agentes, repeticoes, cfg, filtro)

    manifesto = Manifesto(
        rodada=rodada,
        criado_em=datetime.now(UTC).isoformat(timespec="seconds"),
        configs=tuple(c.nome for c in configs),
        conjuntos=("deterministica", *(c for c in CONJUNTOS_COM_AGENTE if c in conjuntos)),
        agentes=tuple(agentes),
        repeticoes=repeticoes,
        flags={"completa": completa},
        versoes=_versoes(imagens, agentes, juiz, imagem_juiz),
        commit_bateria=dep.commit(),
        wheels=_wheels(configs, origens),
        imagens=imagens,
        filtro=filtro,
    )
    pasta = cfg.resultados / rodada
    if (pasta / NOME_MANIFESTO).is_file():
        if diferenca := _diferenca(ler_manifesto(pasta), manifesto):
            raise RodadaInterrompida(
                CODIGO_RECUSA,
                f"a rodada {rodada} não pode ser retomada: {diferenca}; use outro --rodada",
                pasta,
            )
        for sobra in pasta.glob(".trabalho-*"):
            shutil.rmtree(sobra, ignore_errors=True)
    else:
        pasta.mkdir(parents=True, exist_ok=True)
        gravar_manifesto(pasta, manifesto)
    ctl.pasta = pasta
    log = _Log(pasta)
    if ctl.trava_velha is not None:
        log("trava_velha_substituida", pid=ctl.trava_velha)
    log("inicio", execucoes_planejadas=len(planejadas))

    codigo, motivo = _rodar_tudo(
        pasta,
        planejadas,
        cfg,
        orcamento,
        paralelo_por_agente,
        agentes,
        leituras,
        imagem_juiz,
        juiz,
        esperar_limite_min,
        dep,
        ctl,
        log,
    )
    return pasta, log, codigo, motivo


def _rodar_tudo(
    pasta: Path,
    planejadas: list[Planejada],
    cfg: Config,
    orcamento: Orcamento,
    paralelo_por_agente: int,
    agentes: Sequence[str],
    leituras: Mapping[str, tuple[str, ...]],
    imagem_juiz: str,
    juiz: Juiz,
    esperar_limite_min: int | None,
    dep: Dependencias,
    ctl: _Controle,
    log: _Log,
) -> tuple[int, str]:
    det = _deterministica(pasta, cfg, dep, log)
    if det:
        return CODIGO_DETERMINISTICA, det

    for p in planejadas:
        if p.pulado is not None and not _feita(pasta, p.execucao):
            gravar_registro(pasta, _registro_pulado(pasta.name, p))
            log("pulado", execucao=_rotulo(p.execucao), motivo=p.pulado)
    com_executor = [p for p in planejadas if p.pulado is None]

    def avaliar_de(p: Planejada) -> Callable:
        e = p.execucao
        if isinstance(p.fonte, Cenario):
            return avaliar_usuario(
                p.fonte,
                juiz,
                cfg,
                agente=e.agente,
                repeticao=e.repeticao,
                leitura_mcp=leituras.get(e.config, ()),
                imagem=imagem_juiz,
                destino_log=_pasta_da_execucao(pasta, e),
            )
        return avaliar_tools(p.fonte)

    espera = 0
    while True:
        pendentes = [p for p in com_executor if not _feita(pasta, p.execucao)]
        if not pendentes:
            return 0, "rodada completa"
        _rodar_pendentes(
            pasta,
            pendentes,
            cfg,
            orcamento,
            paralelo_por_agente,
            agentes,
            avaliar_de,
            dep,
            ctl,
            log,
        )
        if ctl.parada == "interrompida":
            return CODIGO_INTERROMPIDA, "rodada interrompida (Ctrl-C); retome com o mesmo --rodada"
        if ctl.parada == "limite_repetido":
            return (
                CODIGO_LIMITE,
                f"a mesma execução bateu o limite {SUSPEITAS_DE_LIMITE} vezes enquanto outras "
                "concluíam: provável falso positivo do detector; confira antes de retomar",
            )
        if ctl.parada == "orcamento":
            log("orcamento", iniciadas=ctl.iniciadas)
            return CODIGO_ORCAMENTO, "orçamento da rodada estourado"
        if ctl.parada is None:
            faltam = [p for p in com_executor if not _feita(pasta, p.execucao)]
            if not faltam:
                return 0, "rodada completa"
            return CODIGO_DETERMINISTICA, f"{len(faltam)} execução(ões) sem registro gravado"
        if esperar_limite_min is None:
            return CODIGO_LIMITE, "limite de uso atingido; retome a rodada depois da janela"
        espera += 1
        log("espera_limite", minutos=esperar_limite_min, espera=espera)
        print(f"limite de uso: esperando {esperar_limite_min} min (espera {espera})", flush=True)
        antes = dep.relogio()
        dep.esperar(esperar_limite_min * 60)
        ctl.esperado_s += dep.relogio() - antes
        ctl.parada = None


def _estados_gravados(pasta: Path) -> list[str] | None:
    """Os estados da determinística já concluída, ou `None` quando ela precisa rodar de novo.

    Sem a marca de conclusão, com JSON ilegível ou com `erro_infra` (falha do ambiente, não
    do produto), ela roda de novo; `falhou` é resultado e vale na retomada.
    """
    pasta_det = pasta / "execucoes" / "deterministica"
    if not (pasta_det / MARCA_DETERMINISTICA).is_file():
        return None
    try:
        estados = [
            json.loads(a.read_text(encoding="utf-8"))["estado"]
            for a in sorted(pasta_det.glob(f"*/*/*/*/{NOME_REGISTRO}"))
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not estados or "erro_infra" in estados:
        return None
    return estados


def _deterministica(pasta: Path, cfg: Config, dep: Dependencias, log: _Log) -> str | None:
    estados = _estados_gravados(pasta)
    if estados is None:
        pasta_det = pasta / "execucoes" / "deterministica"
        shutil.rmtree(pasta_det, ignore_errors=True)
        registros = dep.deterministica(pasta, cfg)
        for r in registros:
            gravar_registro(pasta, r)
        pasta_det.mkdir(parents=True, exist_ok=True)
        (pasta_det / MARCA_DETERMINISTICA).write_text("", encoding="utf-8")
        estados = [r.estado for r in registros]
    falhas = sum(e in ("falhou", "erro_infra") for e in estados)
    log("deterministica", testes=len(estados), falhas=falhas)
    print(f"determinística: {len(estados)} testes, {falhas} com falha", flush=True)
    if falhas or not estados:
        return f"determinística com {falhas} falha(s): a rodada para antes dos agentes"
    return None


def _rotulo(e: Execucao) -> str:
    return f"{e.conjunto}/{e.caso}/{e.agente}/{e.config}/{e.repeticao}"


def _registro_pulado(rodada: str, p: Planejada) -> Registro:
    e = p.execucao
    return Registro(
        rodada=rodada,
        conjunto=e.conjunto,
        caso=e.caso,
        agente=e.agente,
        config=e.config,
        repeticao=e.repeticao,
        estado="pulado",
        motivo=p.pulado or "",
        tools=(),
        duracao_s=0.0,
    )


def _rodar_pendentes(
    pasta: Path,
    pendentes: list[Planejada],
    cfg: Config,
    orcamento: Orcamento,
    paralelo_por_agente: int,
    agentes: Sequence[str],
    avaliar_de: Callable[[Planejada], Callable[..., Avaliacao]],
    dep: Dependencias,
    ctl: _Controle,
    log: _Log,
) -> None:
    filas = {a: deque(p for p in pendentes if p.execucao.agente == a) for a in agentes}

    def interrompida() -> bool:
        return ctl.parada == "interrompida"

    def avaliar_ou_parar(p: Planejada) -> Callable[..., Avaliacao]:
        avaliar = avaliar_de(p)

        def guardado(leitura):
            if interrompida():
                raise RuntimeError("rodada interrompida antes da avaliação")
            return avaliar(leitura)

        return guardado

    def limite(e: Execucao, motivo: str) -> None:
        rotulo = _rotulo(e)
        shutil.rmtree(_pasta_da_execucao(pasta, e), ignore_errors=True)
        with ctl.trava:
            ctl.iniciadas -= 1
            ctl.limites_na_passada.append(rotulo)
            if ctl.parada is None:
                ctl.parada = "limite"
        log("limite", execucao=rotulo, motivo=motivo)
        print(f"limite     {rotulo}: {motivo}", flush=True)

    def trabalhador(fila: deque[Planejada]) -> None:
        try:
            _trabalhar(fila)
        # Uma exceção numa thread morreria em silêncio: ela volta para a thread principal,
        # que varre a pasta e a repropaga.
        except Exception as erro:
            with ctl.trava:
                ctl.erro = ctl.erro or erro
                ctl.parada = "erro"

    def _trabalhar(fila: deque[Planejada]) -> None:
        while True:
            with ctl.trava:
                if ctl.parada or not fila:
                    return
                if _estourou(ctl, orcamento, dep.relogio()):
                    ctl.parada = "orcamento"
                    return
                p = fila.popleft()
                ctl.iniciadas += 1
                ctl.em_voo[_rotulo(p.execucao)] = p.execucao
            e = p.execucao
            try:
                shutil.rmtree(_pasta_da_execucao(pasta, e), ignore_errors=True)
                r = dep.executar(e, cfg, pasta, avaliar_ou_parar(p))
            finally:
                with ctl.trava:
                    ctl.em_voo.pop(_rotulo(e), None)
            if interrompida():
                shutil.rmtree(_pasta_da_execucao(pasta, e), ignore_errors=True)
                return
            if _de_limite(r.estado, r.motivo):
                limite(e, r.motivo)
                continue
            with ctl.trava:
                ctl.concluidas_na_passada += 1
            print(f"{r.estado:<10} {_rotulo(e)} ({r.duracao_s:.0f} s)", flush=True)

    ctl.limites_na_passada.clear()
    ctl.concluidas_na_passada = 0
    threads = [
        threading.Thread(target=trabalhador, args=(fila,), daemon=True)
        for fila in filas.values()
        for _ in range(max(1, paralelo_por_agente))
    ]
    try:
        for t in threads:
            t.start()
        for t in threads:
            while t.is_alive():
                t.join(timeout=0.5)
    except KeyboardInterrupt:
        with _sem_ctrl_c():
            with ctl.trava:
                ctl.parada = "interrompida"
                em_voo = list(ctl.em_voo.values())
            log("interrompida", em_voo=[_rotulo(e) for e in em_voo])
            print("interrompida: encerrando os containers em voo", flush=True)
            prefixos = [prefixo_do_container(e, pasta.name) for e in em_voo]
            prefixos += [
                prefixo_do_juiz(_pasta_da_execucao(pasta, e))
                for e in em_voo
                if e.conjunto == "usuario"
            ]
            dep.encerrar_em_voo(cfg, prefixos)
            prazo = time.monotonic() + TEMPO_FIM_THREADS
            for t in threads:
                if t.ident is not None:
                    t.join(timeout=max(0.0, prazo - time.monotonic()))
        return
    if ctl.erro is not None:
        raise ctl.erro
    _contar_suspeitas(ctl, log)


def _contar_suspeitas(ctl: _Controle, log: _Log) -> None:
    """Separa a janela real de limite de um falso positivo do detector.

    Se todas as execuções tentadas bateram o limite, é a janela real: espera de novo, sem
    teto. Se outra concluiu na mesma passada, a que bateu o limite fica mais suspeita; com
    `SUSPEITAS_DE_LIMITE`, a rodada para em vez de gastar a conta esperando à toa.
    """
    if not ctl.limites_na_passada or not ctl.concluidas_na_passada:
        return
    for rotulo in ctl.limites_na_passada:
        ctl.suspeitas[rotulo] = ctl.suspeitas.get(rotulo, 0) + 1
        if ctl.suspeitas[rotulo] >= SUSPEITAS_DE_LIMITE:
            ctl.parada = "limite_repetido"
            log("limite_repetido", execucao=rotulo, suspeitas=ctl.suspeitas[rotulo])


@contextmanager
def _sem_ctrl_c() -> Iterator[None]:
    """Ignora um novo Ctrl-C até a limpeza terminar (só a thread principal recebe sinais)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    anterior = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, anterior)
