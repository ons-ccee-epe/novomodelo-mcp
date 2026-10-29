"""Rodada: a determinística, depois os conjuntos com agente, intercalados por configuração.

A pasta da rodada é `<resultados>/<rodada>`. Uma execução com `registro.json` não roda de
novo; a que bateu no limite de uso do agente ou do juiz tem a pasta apagada, para a
retomada refazê-la. No fim, o gitleaks varre a pasta inteira.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from tests.e2e.config import Config
from tests.e2e.conjuntos.tools.adaptador import avaliar_tools, carregar_casos, para_execucoes
from tests.e2e.conjuntos.usuario.cenario import Cenario, cenarios_da_rodada
from tests.e2e.conjuntos.usuario.juiz import JUIZ_PADRAO, MOTIVO_LIMITE, Juiz, no_manifesto
from tests.e2e.conjuntos.usuario.pontuar import avaliar_usuario
from tests.e2e.executor.casos import CASOS_GRANDES, pasta_preparados, resolver
from tests.e2e.executor.container import ENDURECIMENTO, Execucao, executar
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
ARQUIVO_BLOQUEIO = "BLOQUEADO-SEGREDO.txt"
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
    """Um registro por teste do JUnit XML do pytest: falha e erro viram `falhou`."""
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
        registros.append(
            _registro_deterministica(
                rodada, caso.get("name", ""), estado, motivo, float(caso.get("time") or 0)
            )
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
) -> tuple[str, ...]:
    """As tools de leitura do MCP instalado na imagem, que o cliente roda sem aprovação.

    Raises:
        FalhaPreparo: a imagem não respondeu com a lista de tools.
    """
    if c.wheel is None:
        return ()
    tag = tag_imagem(c, agente)
    cmd = [cfg.motor, "run", "--rm", *ENDURECIMENTO, "--network=none", tag]
    cmd += ["sh", "-c", _PYTHON_DO_MCP, "sh", _LEITURA]
    try:
        feito = rodar(cmd, capture_output=True, text=True, timeout=TEMPO_LEITURA, check=False)
        linhas = feito.stdout.strip().splitlines() if feito.returncode == 0 else []
        nomes = json.loads(linhas[-1]) if linhas else None
    except (OSError, subprocess.SubprocessError, ValueError):
        nomes = None
    if not isinstance(nomes, list) or not all(isinstance(n, str) for n in nomes):
        raise FalhaPreparo(f"tools de leitura do MCP ilegíveis na imagem {tag}")
    return tuple(nomes)


def varrer_segredos(pasta: Path) -> Varredura:
    """Roda `gitleaks dir --redact` na pasta e devolve só os arquivos com achado."""
    exe = shutil.which("gitleaks")
    if exe is None:
        return Varredura(erro="gitleaks fora do PATH: a pasta da rodada não foi varrida")
    with tempfile.TemporaryDirectory(prefix="novomodelo-bateria-gitleaks-") as tmp:
        relatorio = Path(tmp) / "achados.json"
        cmd = [exe, "dir", "--redact", "--no-banner", "--report-format", "json"]
        cmd += ["--report-path", str(relatorio), "--exit-code", "1", str(pasta)]
        try:
            feito = subprocess.run(cmd, capture_output=True, timeout=TEMPO_GITLEAKS, check=False)
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


def _mesma_rodada(a: Manifesto, b: Manifesto) -> bool:
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

    return chave(a) == chave(b)


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


def _feita(pasta: Path, e: Execucao) -> bool:
    """Já tem resultado; um registro de limite de uso (sobra de uma parada) não conta."""
    arquivo = _pasta_da_execucao(pasta, e) / NOME_REGISTRO
    try:
        motivo = json.loads(arquivo.read_text(encoding="utf-8")).get("motivo")
    except (OSError, ValueError, AttributeError):
        return False
    if motivo in MOTIVOS_LIMITE:
        shutil.rmtree(arquivo.parent, ignore_errors=True)
        return False
    return True


@dataclass
class _Controle:
    t0: float
    iniciadas: int = 0
    parada: str | None = None
    trava: threading.Lock = field(default_factory=threading.Lock)


def _estourou(ctl: _Controle, orcamento: Orcamento, agora: float) -> bool:
    if orcamento.max_execucoes and ctl.iniciadas >= orcamento.max_execucoes:
        return True
    return bool(orcamento.max_minutos and agora - ctl.t0 >= orcamento.max_minutos * 60)


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
        RodadaInterrompida: `codigo` 1 (determinística falhou, imagem não ficou pronta
            ou execução sem registro), 2 (retomada com outro plano ou nome inválido), 3 (achado de segredo ou
            varredura que não rodou), 4 (limite de uso, sem `esperar_limite_min`) ou
            5 (orçamento estourado); a pasta, quando existe, já tem o que foi feito.
    """
    dep = dep or Dependencias()
    origens = origens or {}
    rodada = rodada or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if not re.search(PADRAO_NOME, rodada):
        raise RodadaInterrompida(CODIGO_RECUSA, f"nome de rodada inválido: {rodada!r}")
    if not configs:
        raise RodadaInterrompida(CODIGO_RECUSA, "nenhuma configuração do MCP")
    ctl = _Controle(t0=dep.relogio())
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
    )
    pasta = cfg.resultados / rodada
    if (pasta / NOME_MANIFESTO).is_file():
        if not _mesma_rodada(ler_manifesto(pasta), manifesto):
            raise RodadaInterrompida(
                CODIGO_RECUSA,
                f"a rodada {rodada} existe com outro plano ou outras versões; use outro --rodada",
                pasta,
            )
    else:
        pasta.mkdir(parents=True, exist_ok=True)
        gravar_manifesto(pasta, manifesto)
    log = _Log(pasta)
    log("inicio", execucoes_planejadas=len(planejadas))

    try:
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
    finally:
        varredura = dep.varrer(pasta)
    if varredura.erro or varredura.arquivos:
        linhas = [varredura.erro] if varredura.erro else []
        linhas += [f"segredo encontrado em: {a}" for a in varredura.arquivos]
        (pasta / ARQUIVO_BLOQUEIO).write_text("\n".join(linhas) + "\n", encoding="utf-8")
        log("segredo", arquivos=list(varredura.arquivos), erro=varredura.erro)
        raise RodadaInterrompida(
            CODIGO_SEGREDO, f"varredura de segredos bloqueou a rodada: {ARQUIVO_BLOQUEIO}", pasta
        )
    log("fim", codigo=codigo, motivo=motivo)
    if codigo:
        raise RodadaInterrompida(codigo, motivo, pasta)
    return pasta


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
        dep.esperar(esperar_limite_min * 60)
        ctl.parada = None


def _deterministica(pasta: Path, cfg: Config, dep: Dependencias, log: _Log) -> str | None:
    existentes = sorted((pasta / "execucoes" / "deterministica").glob(f"*/*/*/*/{NOME_REGISTRO}"))
    if existentes:
        estados = [json.loads(a.read_text(encoding="utf-8"))["estado"] for a in existentes]
    else:
        registros = dep.deterministica(pasta, cfg)
        for r in registros:
            gravar_registro(pasta, r)
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

    def trabalhador(fila: deque[Planejada]) -> None:
        while True:
            with ctl.trava:
                if ctl.parada or not fila:
                    return
                if _estourou(ctl, orcamento, dep.relogio()):
                    ctl.parada = "orcamento"
                    return
                p = fila.popleft()
                ctl.iniciadas += 1
            e = p.execucao
            r = dep.executar(e, cfg, pasta, avaliar_de(p))
            if r.motivo in MOTIVOS_LIMITE:
                shutil.rmtree(_pasta_da_execucao(pasta, e), ignore_errors=True)
                with ctl.trava:
                    ctl.parada = ctl.parada or "limite"
                log("limite", execucao=_rotulo(e), motivo=r.motivo)
                print(f"limite     {_rotulo(e)}: {r.motivo}", flush=True)
                continue
            print(f"{r.estado:<10} {_rotulo(e)} ({r.duracao_s:.0f} s)", flush=True)

    threads = [
        threading.Thread(target=trabalhador, args=(fila,), daemon=True)
        for fila in filas.values()
        for _ in range(max(1, paralelo_por_agente))
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
