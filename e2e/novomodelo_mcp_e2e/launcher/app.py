"""App FastAPI do launcher de dev.

Rotas (todas sob /api, exceto o serving de dados):
  GET  /api/cases              -> biblioteca de prompts (casos de teste)
  GET  /api/command-preview    -> comando equivalente de `python -m novomodelo_mcp_e2e rodar`
  POST /api/rodadas            -> dispara a bateria (opções da lista branca, sem shell)
  GET  /api/rodadas            -> rodadas gravadas em Config.resultados
  GET  /api/rodadas/{id}       -> manifesto, registros e decisão sem base de uma rodada
  GET  /api/load-tools         -> tools do catálogo de carga (e as barradas) e limites
  GET  /api/load-cases         -> casos por agente que podem entrar na carga e limites do modo agent
  GET  /api/load-capacity      -> sessões simultâneas recomendadas para a máquina e a seleção
  POST /api/load-runs          -> dispara um teste de carga (modo tools ou agent)
  GET  /api/load-runs          -> lista cargas desta sessao do launcher
  GET  /api/load-runs/{id}     -> estado de uma carga (progresso ao vivo, polling)
  POST /api/load-runs/{id}/cancel -> para a carga e mata os servidores MCP
  GET  /api/baselines          -> baseline vigente de cada conjunto
  PUT  /api/baselines/{conjunto} -> define a bateria baseline do conjunto
  DELETE /api/baselines/{conjunto} -> remove a baseline do conjunto
  GET  /api/health            -> saude do launcher

  GET  /data/results/...       -> JSON das baterias (mesma convencao do plugin Vite);
                                  as cargas ficam em /data/results/load/
  GET  /data/metrics/...       -> history.jsonl

Seguranca de dev:
  - Bind SEMPRE em 127.0.0.1 (feito pelo runner uvicorn, nao aqui).
  - CORS liberado apenas para http://127.0.0.1:5174 (o dev server do Vite).
  - Host header restrito a 127.0.0.1/localhost (anti DNS rebinding: sem isso,
    uma pagina que resolve para 127.0.0.1 vira same-origin e dispara agentes).
  - POSTs exigem o header X-Launcher, que um form ou request cross-origin
    simples nao consegue enviar sem preflight.
  - Um run por vez (rodada ou carga, na mesma trava); valores do disparo validados.
  - Serving de /data confinado as raizes results/ e metrics/ (anti path traversal).
"""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from novomodelo_mcp_e2e.launcher.command_preview import command_preview
from novomodelo_mcp_e2e.launcher.load_service import LoadRunService
from novomodelo_mcp_e2e.launcher.run_gate import RunGate
from novomodelo_mcp_e2e.launcher.service import (
    PADRAO_DE_NOME,
    RecusaDeDisparo,
    RodadaRequest,
    RodadaService,
    RunAlreadyActiveError,
    resolver_wheel,
)
from novomodelo_mcp_e2e.load.agent_cases import (
    CaseSelection,
    describe_cases,
    load_cases,
    select_cases,
)
from novomodelo_mcp_e2e.load.agent_engine import MAX_AGENT_CONCURRENCY, AgentLoadConfig
from novomodelo_mcp_e2e.load.capacity import cases_profile, estimate_capacity, tools_profile
from novomodelo_mcp_e2e.load.engine import (
    DEFAULT_TIMEOUT_S,
    MAX_CONCURRENCY,
    MAX_DURATION_S,
    MAX_ITERATIONS,
    MAX_TIMEOUT_S,
    MIN_CONCURRENCY,
    MIN_DURATION_S,
    LoadConfig,
)
from novomodelo_mcp_e2e.load.mix import ALLOWED_TOOLS, describe_catalog, validate_tools
from novomodelo_mcp_e2e.load.store import LoadStore
from novomodelo_mcp_e2e.queries.loader import CasesLoaderError
from novomodelo_mcp_e2e.queries.store import ResultStore

__all__ = ["app", "create_app"]

# base_dir = e2e/novomodelo_mcp_e2e/
_BASE_DIR = Path(__file__).resolve().parent.parent
_RESULTS_DIR = (_BASE_DIR / "results").resolve()
_METRICS_DIR = (_BASE_DIR / "metrics").resolve()
_DATA_ROOTS = {"results": _RESULTS_DIR, "metrics": _METRICS_DIR}
_FIXTURES_DIR = _BASE_DIR / "fixtures"
_CASE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
_GROUP_PATTERN = r"^[a-z][a-z0-9_-]*$"
_MCP_PATTERN = r"^(sem|[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\.whl)$"
_AGENT_ONLY_FIELDS = ("provider", "mcp", "case_id", "group", "tags")

# Origens permitidas para o dev server do Vite (localhost apenas).
_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5174",
    "http://localhost:5174",
]


_ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
LAUNCHER_HEADER = "X-Launcher"


def _require_launcher_header(
    x_launcher: str | None = Header(default=None, alias=LAUNCHER_HEADER),
) -> None:
    if x_launcher != "1":
        raise HTTPException(status_code=403, detail=f"header {LAUNCHER_HEADER} ausente")


def _within(root: Path, target: Path) -> bool:
    # is_relative_to, nao startswith: "results2" passaria num prefixo de string.
    return target.is_relative_to(root)


class BaselineRequest(BaseModel):
    """Corpo de PUT /api/baselines/{conjunto}."""

    batch_id: str = Field(min_length=1, max_length=200, pattern=_CASE_ID_PATTERN)


class LoadRunRequest(BaseModel):
    """Corpo de POST /api/load-runs. Campos desconhecidos são recusados.

    ``mode`` tools (padrão): ``tools`` escolhe o mix. ``mode`` agent: ``provider`` (None =
    o primeiro instalado) e no máximo um entre ``case_id``, ``group`` e ``tags``; o teto de
    sessões simultâneas é o do modo agent.
    """

    model_config = ConfigDict(extra="forbid")

    mode: Literal["tools", "agent"] = "tools"
    concurrency: int = Field(ge=MIN_CONCURRENCY, le=MAX_CONCURRENCY)
    duration_seconds: float = Field(ge=MIN_DURATION_S, le=MAX_DURATION_S, allow_inf_nan=False)
    iterations: int | None = Field(default=None, ge=1, le=MAX_ITERATIONS)
    tools: list[str] | None = Field(default=None, min_length=1, max_length=len(ALLOWED_TOOLS))
    timeout_seconds: float | None = Field(default=None, gt=0, le=MAX_TIMEOUT_S, allow_inf_nan=False)
    provider: Literal["kiro-cli", "claude"] | None = None
    mcp: str | None = Field(default=None, max_length=200, pattern=_MCP_PATTERN)
    case_id: str | None = Field(default=None, max_length=200, pattern=_CASE_ID_PATTERN)
    group: str | None = Field(default=None, max_length=40, pattern=_GROUP_PATTERN)
    tags: list[str] | None = Field(default=None, min_length=1, max_length=20)

    @field_validator("tools")
    @classmethod
    def _only_catalog_tools(cls, tools: list[str] | None) -> list[str] | None:
        # Allow-list aqui, antes de qualquer processo: o body não escolhe o que o motor chama.
        return validate_tools(tools) if tools is not None else None

    @field_validator("tags")
    @classmethod
    def _plain_tags(cls, tags: list[str] | None) -> list[str] | None:
        if tags is None:
            return None
        bad = [t for t in tags if not re.fullmatch(_GROUP_PATTERN, t) or len(t) > 40]
        if bad:
            raise ValueError(f"tags inválidas: {', '.join(bad[:5])}")
        return tags

    @model_validator(mode="after")
    def _fields_of_the_mode(self) -> LoadRunRequest:
        if self.mode == "tools":
            given = [name for name in _AGENT_ONLY_FIELDS if getattr(self, name) is not None]
            if given:
                raise ValueError(f"{', '.join(given)} só vale(m) no modo agent")
            return self
        if self.tools is not None:
            raise ValueError("tools só vale no modo tools")
        if self.concurrency > MAX_AGENT_CONCURRENCY:
            raise ValueError(
                f"sessões simultâneas acima do teto do modo agent ({MAX_AGENT_CONCURRENCY})"
            )
        self.selection()
        return self

    def selection(self) -> CaseSelection:
        """Seleção de casos do modo agent.

        Raises:
            ValueError: Se mais de um entre caso, grupo e tags foi dado.
        """
        tags = tuple(self.tags) if self.tags else None
        return CaseSelection(case_id=self.case_id, group=self.group, tags=tags)

    def to_config(self, provider: str | None = None) -> LoadConfig | AgentLoadConfig:
        if self.mode == "agent":
            return AgentLoadConfig(
                mcp=self.mcp,
                concurrency=self.concurrency,
                duration_s=self.duration_seconds,
                provider=provider or self.provider,
                selection=self.selection(),
                iterations=self.iterations,
                timeout_s=self.timeout_seconds,
            )
        return LoadConfig(
            concurrency=self.concurrency,
            duration_s=self.duration_seconds,
            iterations=self.iterations,
            tools=tuple(self.tools) if self.tools is not None else None,
            timeout_s=self.timeout_seconds
            if self.timeout_seconds is not None
            else DEFAULT_TIMEOUT_S,
        )


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


def _agent_provider(requested: str | None, mcp: str | None) -> str:
    """Provedor da carga do modo agent (padrão claude); 422 se a wheel pedida não está na pasta."""
    if mcp is not None and mcp != "sem":
        try:
            resolver_wheel(mcp)
        except RecusaDeDisparo as exc:
            raise _unprocessable(str(exc)) from exc
    return requested or "claude"


def _check_agent_selection(selection: CaseSelection) -> None:
    """422 se a seleção não existe ou nenhum caso dela pode rodar na carga."""
    chosen = _agent_selection(selection)
    if not chosen.cases:
        reasons = "; ".join(f"{e.id}: {e.reason}" for e in chosen.excluded[:5])
        raise _unprocessable(
            f"nenhum caso da seleção ({selection.describe()}) pode rodar na carga: {reasons}"
        )


def _agent_selection(selection: CaseSelection):
    """Casos elegíveis e excluídos da seleção; 422 se ela não existe."""
    try:
        return select_cases(load_cases(_FIXTURES_DIR), selection)
    except (CasesLoaderError, ValueError) as exc:
        raise _unprocessable(str(exc)) from exc


def _split(raw: str | None) -> list[str] | None:
    names = [part.strip() for part in (raw or "").split(",") if part.strip()]
    return names or None


def _capacity_profile(
    mode: str, tools: str | None, case_id: str | None, group: str | None, tags: str | None
):
    """Perfil da seleção para o limitador; 422 se a seleção é inválida ou é de outro modo."""
    if mode == "tools":
        if case_id or group or tags:
            raise _unprocessable("case_id, group e tags só valem no modo agent")
        try:
            return tools_profile(_FIXTURES_DIR, _split(tools))
        except ValueError as exc:
            raise _unprocessable(str(exc)) from exc
    if tools:
        raise _unprocessable("tools só vale no modo tools")
    try:
        selection = CaseSelection(case_id=case_id, group=group, tags=tuple(_split(tags) or ()))
    except ValueError as exc:
        raise _unprocessable(str(exc)) from exc
    return cases_profile(_FIXTURES_DIR, _agent_selection(selection).cases)


def create_app() -> FastAPI:
    app = FastAPI(
        title="novomodelo-mcp E2E Launcher (dev)",
        description=(
            "Launcher de desenvolvimento que dispara os testes das tools MCP "
            "pelo executor em container. Nao e backend de producao."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", LAUNCHER_HEADER],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_ALLOWED_HOSTS)

    @app.exception_handler(RequestValidationError)
    def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        # Sem o "input": o handler padrão ecoa o valor recebido e um inf/NaN
        # quebra a serialização, virando 500 em vez de 422. O "ctx" de um
        # validador que levanta ValueError carrega a exceção, também não serializável.
        errors = [
            {
                k: ({ck: str(cv) for ck, cv in v.items()} if k == "ctx" else v)
                for k, v in e.items()
                if k != "input"
            }
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": errors})

    gate = RunGate()
    service = RodadaService(gate=gate)
    load_service = LoadRunService(gate=gate)

    # ---- meta ------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/baselines")
    def baselines() -> dict[str, Any]:
        return {"baselines": ResultStore(_RESULTS_DIR, _METRICS_DIR).get_baselines()}

    @app.put("/api/baselines/{conjunto:path}", dependencies=[Depends(_require_launcher_header)])
    def put_baseline(conjunto: str, body: BaselineRequest) -> dict[str, Any]:
        store = ResultStore(_RESULTS_DIR, _METRICS_DIR)
        try:
            store.set_baseline(body.batch_id, conjunto)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="bateria nao encontrada") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"conjunto": conjunto, "batch_id": body.batch_id}

    @app.delete("/api/baselines/{conjunto:path}", dependencies=[Depends(_require_launcher_header)])
    def delete_baseline(conjunto: str) -> dict[str, Any]:
        removed = ResultStore(_RESULTS_DIR, _METRICS_DIR).clear_baseline(conjunto)
        return {"conjunto": conjunto, "removed": removed}

    @app.get("/api/cases")
    def cases() -> dict[str, Any]:
        """Biblioteca de prompts: casos de teste disponiveis."""
        try:
            return {"cases": service.list_cases_meta()}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ---- rodadas ---------------------------------------------------------

    @app.post("/api/rodadas", dependencies=[Depends(_require_launcher_header)])
    def start_rodada(req: RodadaRequest) -> dict[str, Any]:
        """Dispara `python -m novomodelo_mcp_e2e rodar` com as opções validadas.

        422 se a wheel não está na pasta configurada; 409 se há outro run ativo.
        """
        try:
            return service.disparar(req)
        except RecusaDeDisparo as exc:
            raise _unprocessable(str(exc)) from exc
        except RunAlreadyActiveError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/rodadas")
    def list_rodadas() -> dict[str, Any]:
        return {"rodadas": service.listar()}

    @app.get("/api/rodadas/{rodada}")
    def get_rodada(rodada: str) -> dict[str, Any]:
        if not re.search(PADRAO_DE_NOME, rodada):
            raise _unprocessable("nome de rodada inválido")
        detalhe = service.detalhe(rodada)
        if detalhe is None:
            raise HTTPException(status_code=404, detail="rodada nao encontrada")
        return detalhe

    @app.get("/api/command-preview")
    def get_command_preview(
        mcp: Annotated[list[str] | None, Query(max_length=8)] = None,
        conjuntos: str | None = Query(None, max_length=40),
        agentes: str | None = Query(None, max_length=40),
        filtro: str | None = Query(None, max_length=400),
        repeticoes: int | None = Query(None),
        completa: bool = Query(False),
    ) -> dict[str, Any]:
        """Comando que um disparo com estas opções executaria; nada é iniciado nem gravado."""
        try:
            req = RodadaRequest.model_validate(
                {
                    "mcp": mcp or ["sem"],
                    "conjuntos": _split(conjuntos),
                    "agentes": _split(agentes),
                    "filtro": filtro,
                    "repeticoes": repeticoes,
                    "completa": completa,
                }
            )
        except ValidationError as exc:
            raise _unprocessable("; ".join(e["msg"] for e in exc.errors())) from exc
        return command_preview(req)

    # ---- cargas ----------------------------------------------------------

    @app.get("/api/load-cases")
    def load_cases_route() -> dict[str, Any]:
        """Casos por agente, se podem entrar na carga (e por quê não) e os limites do modo agent."""
        try:
            cases = describe_cases(load_cases(_FIXTURES_DIR))
        except CasesLoaderError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "cases": cases,
            "limits": {
                "min_concurrency": MIN_CONCURRENCY,
                "max_concurrency": MAX_AGENT_CONCURRENCY,
                "min_duration_seconds": MIN_DURATION_S,
                "max_duration_seconds": MAX_DURATION_S,
                "max_iterations": MAX_ITERATIONS,
                "max_timeout_seconds": MAX_TIMEOUT_S,
                "default_timeout_seconds": None,
            },
        }

    @app.get("/api/load-capacity")
    def load_capacity(
        mode: Literal["tools", "agent"] = Query("tools"),
        provider: Literal["kiro-cli", "claude"] | None = Query(None),
        tools: str | None = Query(None, max_length=2000),
        case_id: str | None = Query(None, max_length=200, pattern=_CASE_ID_PATTERN),
        group: str | None = Query(None, max_length=40, pattern=_GROUP_PATTERN),
        tags: str | None = Query(None, max_length=800),
    ) -> dict[str, Any]:
        """Sessões simultâneas recomendadas para esta máquina e esta seleção (tools: lista
        separada por vírgula, omitida = mix padrão; agent: um entre caso, grupo e tags), o
        fator limitante (teto, memória, CPU ou disco) e a conta."""
        profile = _capacity_profile(mode, tools, case_id, group, tags)
        return estimate_capacity(mode, provider, store=LoadStore(_RESULTS_DIR), profile=profile)

    @app.get("/api/load-tools")
    def load_tools() -> dict[str, Any]:
        """Tools do catálogo de carga (se há fonte, se gravam, se são pesadas, se são do mix
        padrão), as barradas com o motivo, e os limites aceitos."""
        return {
            "tools": describe_catalog(_FIXTURES_DIR),
            "limits": {
                "min_concurrency": MIN_CONCURRENCY,
                "max_concurrency": MAX_CONCURRENCY,
                "min_duration_seconds": MIN_DURATION_S,
                "max_duration_seconds": MAX_DURATION_S,
                "max_iterations": MAX_ITERATIONS,
                "max_timeout_seconds": MAX_TIMEOUT_S,
                "default_timeout_seconds": DEFAULT_TIMEOUT_S,
            },
        }

    @app.post("/api/load-runs", dependencies=[Depends(_require_launcher_header)])
    def start_load_run(req: LoadRunRequest) -> dict[str, Any]:
        """Dispara um teste de carga; 422 se a wheel não está na pasta configurada ou nenhum caso
        da seleção pode rodar, 409 se qualquer outro run estiver ativo."""
        provider = None
        if req.mode == "agent":
            provider = _agent_provider(req.provider, req.mcp)
            _check_agent_selection(req.selection())
        try:
            state = load_service.start_run(req.to_config(provider))
        except RunAlreadyActiveError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return state.to_dict()

    @app.get("/api/load-runs")
    def list_load_runs() -> dict[str, Any]:
        return {"runs": load_service.list()}

    @app.get("/api/load-runs/{run_id}")
    def get_load_run(run_id: str) -> dict[str, Any]:
        state = load_service.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="carga nao encontrada")
        return state.to_dict()

    @app.post("/api/load-runs/{run_id}/cancel", dependencies=[Depends(_require_launcher_header)])
    def cancel_load_run(run_id: str) -> dict[str, Any]:
        """Para a carga e encerra todos os processos do servidor; nada é gravado."""
        state = load_service.cancel(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="carga nao encontrada")
        return state.to_dict()

    # ---- serving dos dados (mesma convencao do plugin de dev do Vite) ----

    @app.get("/data/{bucket}/{name:path}")
    def data(bucket: str, name: str):
        root = _DATA_ROOTS.get(bucket)
        if root is None:
            raise HTTPException(status_code=404, detail="bucket desconhecido")

        target = (root / name).resolve()
        if not _within(root, target):
            raise HTTPException(status_code=403, detail="fora da raiz")
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="nao encontrado")

        text = target.read_text(encoding="utf-8")
        if target.suffix == ".json":
            return JSONResponse(content=_raw_json(text))
        # .jsonl e outros: texto cru.
        media = mimetypes.guess_type(str(target))[0] or "text/plain"
        return PlainTextResponse(content=text, media_type=media)

    @app.get("/data/{bucket}/")
    def data_index(bucket: str) -> dict[str, Any]:
        root = _DATA_ROOTS.get(bucket)
        if root is None:
            raise HTTPException(status_code=404, detail="bucket desconhecido")
        if not root.exists():
            return {"files": []}
        files = [p.name for p in root.iterdir() if p.is_file() and p.suffix in (".json", ".jsonl")]
        return {"files": files}

    return app


def _raw_json(text: str) -> Any:
    """Parseia o texto como JSON para devolver como JSONResponse.

    Se por acaso nao for JSON valido, devolve como string crua dentro de um
    envelope de erro — nunca levanta para o caller.
    """
    import json

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "json invalido no arquivo"}


app = create_app()
