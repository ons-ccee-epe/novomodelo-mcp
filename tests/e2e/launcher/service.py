"""Serviço das rodadas da bateria: dispara `python -m tests.e2e rodar` e lê o que ela gravou.

O disparo monta a lista de argumentos a partir de uma lista branca de opções, cada uma
com o valor validado (`RodadaRequest`); nada passa por shell e nenhum texto livre chega
à linha de comando. O processo roda desanexado do launcher, com o log da bateria num
arquivo, e a vaga de "um run por vez" (`RunGate`) segura o disparo seguinte até ele sair.

A leitura (`listar`, `detalhe`) vem de `Config.resultados`: manifesto, registros e a
decisão do critério sem base de comparação.
"""

from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import jsonschema
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tests.e2e.config import Config, carregar_config
from tests.e2e.go_no_go.criterio import decidir
from tests.e2e.launcher.run_gate import RunAlreadyActiveError, RunGate
from tests.e2e.queries.loader import CasesLoader
from tests.e2e.queries.models import QueryTestCase
from tests.e2e.resultado.armazenamento import PADRAO_NOME, ler_manifesto, ler_registros
from tests.e2e.resultado.modelos import VersaoDesconhecida
from tests.e2e.rodada import (
    ARQUIVO_BLOQUEIO,
    CONFIG_DETERMINISTICA,
    Varredura,
    trava_viva,
    varrer_segredos,
)
from tests.e2e.textos import sem_caminhos

__all__ = [
    "PADRAO_DE_NOME",
    "AMBIENTE_PERMITIDO",
    "PASTA_LOGS",
    "PASTA_WHEELS_ENV",
    "RecusaDeDisparo",
    "RodadaRequest",
    "RodadaService",
    "RunAlreadyActiveError",
    "argumentos_do_rodar",
    "comando_equivalente",
    "resolver_wheel",
]

PASTA_WHEELS_ENV = "NOVOMODELO_LAUNCHER_PASTA_WHEELS"
PASTA_LOGS = ".launcher"
PADRAO_DE_NOME = PADRAO_NOME
NOME_DA_RODADA = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"
NOME_DE_WHEEL = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\.whl$"
FILTRO = r"^[A-Za-z0-9][A-Za-z0-9_.*?-]*(,[A-Za-z0-9_.*?-]+)*$"
MCP_SEM = "sem"
ENTRADA_DO_COMANDO = "python -m tests.e2e rodar"

_BASE_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASES_PATH = _BASE_DIR / "queries" / "cases.yaml"
_FIXTURES_DIR = _BASE_DIR / "fixtures"
_FORMATO_DA_RODADA = "%Y%m%dT%H%M%SZ"
_CAMPOS_DO_RESUMO = (
    "rodada",
    "criado_em",
    "configs",
    "conjuntos",
    "agentes",
    "repeticoes",
    "filtro",
    "commit_bateria",
)


class RecusaDeDisparo(ValueError):
    """O pedido de rodada pede algo fora da lista branca."""


class RodadaRequest(BaseModel):
    """Corpo de `POST /api/rodadas`. Campo desconhecido é recusado."""

    model_config = ConfigDict(extra="forbid")

    rodada: str | None = Field(default=None, pattern=NOME_DA_RODADA)
    mcp: list[str] = Field(min_length=1, max_length=8)
    conjuntos: list[Literal["tools", "usuario"]] | None = Field(default=None, max_length=2)
    agentes: list[Literal["claude", "kiro"]] | None = Field(default=None, max_length=2)
    filtro: str | None = Field(default=None, max_length=400, pattern=FILTRO)
    repeticoes: int | None = Field(default=None, ge=1, le=50)
    completa: bool = False
    max_execucoes: int | None = Field(default=None, ge=0, le=100_000)
    max_minutos: int | None = Field(default=None, ge=0, le=100_000)
    esperar_limite: int | None = Field(default=None, ge=1, le=1_440)
    paralelo_por_agente: int | None = Field(default=None, ge=1, le=16)

    @field_validator("mcp")
    @classmethod
    def _sem_ou_wheel(cls, valores: list[str]) -> list[str]:
        for valor in valores:
            if valor != MCP_SEM and not re.fullmatch(NOME_DE_WHEEL, valor):
                raise ValueError("mcp: 'sem' ou o nome de uma wheel da pasta configurada")
        return list(dict.fromkeys(valores))


def resolver_wheel(nome: str, env: Mapping[str, str] | None = None) -> Path:
    """O arquivo da wheel `nome`, dentro da pasta que o launcher tem configurada.

    Raises:
        RecusaDeDisparo: a pasta não está configurada, o nome não é de uma wheel ou o
            arquivo não existe dentro da pasta (links para fora também são recusados).
    """
    bruto = (env if env is not None else os.environ).get(PASTA_WHEELS_ENV)
    if not bruto:
        raise RecusaDeDisparo(
            f"sem a pasta de wheels ({PASTA_WHEELS_ENV}), só 'sem' é aceito em mcp"
        )
    if not re.fullmatch(NOME_DE_WHEEL, nome):
        raise RecusaDeDisparo(f"nome de wheel inválido: {nome!r}")
    pasta = Path(bruto).expanduser().resolve()
    alvo = (pasta / nome).resolve()
    if not alvo.is_relative_to(pasta) or not alvo.is_file():
        raise RecusaDeDisparo(f"wheel não encontrada na pasta configurada: {nome}")
    return alvo


def argumentos_do_rodar(
    req: RodadaRequest, wheel: Callable[[str], str], rodada: str | None = None
) -> list[str]:
    """Os argumentos de `rodar`, na ordem do pedido; `wheel` decide como cada wheel aparece."""
    args = ["--mcp", *(valor if valor == MCP_SEM else wheel(valor) for valor in req.mcp)]
    if nome := rodada or req.rodada:
        args += ["--rodada", nome]
    if req.conjuntos:
        args += ["--conjuntos", ",".join(req.conjuntos)]
    if req.agentes:
        args += ["--agentes", ",".join(req.agentes)]
    if req.filtro:
        args.append(f"--filtro={req.filtro}")
    if req.repeticoes is not None:
        args += ["--repeticoes", str(req.repeticoes)]
    if req.completa:
        args.append("--completa")
    for opcao, valor in (
        ("--max-execucoes", req.max_execucoes),
        ("--max-minutos", req.max_minutos),
        ("--esperar-limite", req.esperar_limite),
        ("--paralelo-por-agente", req.paralelo_por_agente),
    ):
        if valor is not None:
            args += [opcao, str(valor)]
    return args


def comando_equivalente(req: RodadaRequest) -> dict[str, Any]:
    """O comando que o disparo executaria; as wheels aparecem pelo nome do arquivo."""
    args = argumentos_do_rodar(req, wheel=lambda nome: nome)
    texto = ENTRADA_DO_COMANDO + "".join(f" {_aspas(a)}" for a in args)
    return {"comando": sem_caminhos(texto), "argumentos": args}


def _aspas(arg: str) -> str:
    return arg if re.fullmatch(r"[A-Za-z0-9_.,*=+-]+", arg) else f"'{arg}'"


def _desanexado() -> dict[str, Any]:
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x8) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200
        )
        return {"creationflags": flags}
    return {"start_new_session": True}


AMBIENTE_PERMITIDO = (
    "PATH",
    "HOME",
    "USERPROFILE",
    "LANG",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SYSTEMROOT",
    "APPDATA",
    "LOCALAPPDATA",
    "VIRTUAL_ENV",
)
PREFIXOS_DO_AMBIENTE = (
    "NOVOMODELO_BATERIA_",
    "NOVOMODELO_LAUNCHER_",
    "LC_",
    "XDG_",
    "UV_",
    "CONTAINERS_",
)


def ambiente_do_subprocesso(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """O ambiente da rodada: só `AMBIENTE_PERMITIDO` e os prefixos de `PREFIXOS_DO_AMBIENTE`.

    O resto do ambiente do launcher (tokens, chaves de nuvem) não chega ao processo da
    bateria; o token do Claude entra por arquivo e secret do motor, não por variável.
    """
    origem = env if env is not None else os.environ
    ambiente = {
        k: v
        for k, v in origem.items()
        if k in AMBIENTE_PERMITIDO or k.startswith(PREFIXOS_DO_AMBIENTE)
    }
    ambiente["PYTHONUNBUFFERED"] = "1"
    return ambiente


def _agora() -> str:
    return datetime.now(UTC).isoformat()


class RodadaService:
    """Dispara rodadas desanexadas e lê as rodadas gravadas em `Config.resultados`."""

    def __init__(
        self,
        gate: RunGate | None = None,
        config: Callable[[], Config] = lambda: carregar_config(os.environ),
        cwd: Path = _REPO_ROOT,
        varrer: Callable[[Path], Varredura] | None = None,
    ) -> None:
        self._gate = gate or RunGate()
        self._config = config
        self._cwd = cwd
        self._varrer = varrer
        self._disparos: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    # ---- disparo -----------------------------------------------------------

    def disparar(self, req: RodadaRequest) -> dict[str, Any]:
        """Sobe `python -m tests.e2e rodar` desanexado e devolve o estado do disparo.

        Raises:
            RecusaDeDisparo: wheel fora da pasta configurada.
            RunAlreadyActiveError: outro run (rodada ou carga) está ativo.
        """
        nome = req.rodada or datetime.now(UTC).strftime(_FORMATO_DA_RODADA)
        args = argumentos_do_rodar(req, wheel=lambda n: str(resolver_wheel(n)), rodada=nome)
        cfg = self._config()
        if (dono := trava_viva(cfg.resultados / nome)) is not None:
            raise RunAlreadyActiveError(f"a rodada {nome} já está em andamento (PID {dono})")
        self._gate.acquire(nome)
        try:
            log = self._abrir_log(cfg, nome)
            try:
                processo = subprocess.Popen(
                    [sys.executable, "-m", "tests.e2e", "rodar", *args],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=self._cwd,
                    env=ambiente_do_subprocesso(),
                    shell=False,
                    **_desanexado(),
                )
            finally:
                log.close()
        except BaseException:
            self._gate.release(nome)
            raise
        estado = {
            "rodada": nome,
            "status": "em_andamento",
            "iniciada_em": _agora(),
            "finalizada_em": None,
            "codigo_saida": None,
            "log": f"{PASTA_LOGS}/{nome}.log",
            "comando": comando_equivalente(req)["comando"],
        }
        with self._lock:
            self._disparos[nome] = estado
        threading.Thread(
            target=self._esperar,
            args=(nome, processo, cfg.resultados / PASTA_LOGS),
            name=f"rodada-{nome}",
            daemon=True,
        ).start()
        return dict(estado)

    @staticmethod
    def _abrir_log(cfg: Config, nome: str):
        pasta = cfg.resultados / PASTA_LOGS
        pasta.mkdir(parents=True, exist_ok=True)
        fd = os.open(pasta / f"{nome}.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        return os.fdopen(fd, "ab")

    def _esperar(self, nome: str, processo: subprocess.Popen, pasta_logs: Path) -> None:
        codigo = None
        bloqueado = False
        try:
            codigo = processo.wait()
            bloqueado = self._varrer_log(nome, pasta_logs)
        finally:
            try:
                with self._lock:
                    estado = self._disparos[nome]
                    estado["status"] = "finalizada"
                    estado["finalizada_em"] = _agora()
                    estado["codigo_saida"] = codigo if isinstance(codigo, int) else None
                    estado["log_bloqueado"] = bloqueado
            finally:
                self._gate.release(nome)

    def _varrer_log(self, nome: str, pasta_logs: Path) -> bool:
        """Varre a pasta de logs com o gitleaks; achado ou varredura que não rodou apaga o log."""
        varredura = (self._varrer or varrer_segredos)(pasta_logs)
        if not (varredura.erro or varredura.arquivos):
            return False
        (pasta_logs / f"{nome}.log").write_text(
            "log removido: a varredura de segredos acusou achado ou não rodou\n", encoding="utf-8"
        )
        return True

    # ---- leitura -----------------------------------------------------------

    def listar(self) -> list[dict[str, Any]]:
        """Resumo de cada rodada gravada, da mais recente para a mais antiga pelo nome."""
        pasta = self._config().resultados
        if not pasta.is_dir():
            return []
        resumos = []
        for filha in sorted(pasta.iterdir(), key=lambda p: p.name, reverse=True):
            if not filha.is_dir() or not re.search(PADRAO_NOME, filha.name):
                continue
            if not (filha / "manifesto.json").is_file():
                continue
            resumos.append(self._resumo(filha))
        return resumos

    def detalhe(self, rodada: str) -> dict[str, Any] | None:
        """Manifesto, registros e decisão por configuração; `None` se a rodada não existe.

        Raises:
            ValueError: o nome não segue o padrão de nome de rodada.
        """
        if not re.search(PADRAO_NOME, rodada):
            raise ValueError(f"nome de rodada inválido: {rodada!r}")
        pasta = self._config().resultados / rodada
        if not (pasta / "manifesto.json").is_file():
            return None
        resumo = self._resumo(pasta)
        if "erro" in resumo:
            return {**resumo, "registros": [], "decisoes": {}}
        if resumo["bloqueada"]:
            return {**resumo, "registros": [], "decisoes": {}}
        try:
            manifesto = ler_manifesto(pasta)
            registros = ler_registros(pasta)
        except (OSError, ValueError, VersaoDesconhecida, jsonschema.ValidationError) as erro:
            return {**resumo, "erro": self._erro(erro, pasta), "registros": [], "decisoes": {}}
        decisoes = {}
        for config in manifesto.configs:
            alvo = [r for r in registros if r.config in (config, CONFIG_DETERMINISTICA)]
            try:
                decisoes[config] = dataclasses.asdict(decidir(alvo, None))
            except ValueError as erro:
                decisoes[config] = {"erro": self._erro(erro, pasta)}
        return {
            **resumo,
            "manifesto": manifesto.para_dict(),
            "registros": [r.para_dict() for r in registros],
            "decisoes": decisoes,
        }

    def _resumo(self, pasta: Path) -> dict[str, Any]:
        base: dict[str, Any] = {
            "rodada": pasta.name,
            "bloqueada": (pasta / ARQUIVO_BLOQUEIO).exists(),
            "disparo": self._disparo(pasta.name),
            "em_andamento": trava_viva(pasta) is not None,
        }
        try:
            manifesto = ler_manifesto(pasta).para_dict()
        except (OSError, ValueError, VersaoDesconhecida, jsonschema.ValidationError) as erro:
            return {**base, "erro": self._erro(erro, pasta)}
        return {**base, **{campo: manifesto.get(campo) for campo in _CAMPOS_DO_RESUMO}}

    def _disparo(self, nome: str) -> dict[str, Any] | None:
        with self._lock:
            estado = self._disparos.get(nome)
            return None if estado is None else dict(estado)

    @staticmethod
    def _erro(erro: BaseException, pasta: Path) -> str:
        detalhe = erro.message if isinstance(erro, jsonschema.ValidationError) else str(erro)
        return sem_caminhos(f"resultado ilegível: {detalhe}", (pasta, pasta.parent))

    # ---- casos --------------------------------------------------------------

    @staticmethod
    def load_cases(case_id: str | None = None) -> list[QueryTestCase]:
        """Os casos do conjunto de tools (opcionalmente um só).

        Raises:
            CasesLoaderError: o YAML não carrega ou não valida.
        """
        return CasesLoader(_CASES_PATH, _FIXTURES_DIR).load(case_id=case_id)

    def list_cases_meta(self) -> list[dict[str, Any]]:
        """Metadados dos casos para a biblioteca de prompts da UI."""
        return [
            {
                "id": c.id,
                "query": c.query,
                "expected_tool": c.expected.tool,
                "expected_tools": c.expected.tools,
                "tags": list(c.tags),
                "timeout_s": c.timeout_s,
                "requires": list(c.requires),
            }
            for c in self.load_cases()
        ]
