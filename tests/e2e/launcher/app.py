"""App FastAPI do launcher de dev.

Rotas (todas sob /api, exceto o serving de dados):
  GET  /api/providers          -> provedores de IA detectados no PATH
  GET  /api/cases              -> biblioteca de prompts (casos de teste)
  POST /api/runs               -> dispara uma bateria (esteira completa / tags / 1 caso)
  GET  /api/runs               -> lista runs desta sessao do launcher
  GET  /api/runs/{run_id}      -> estado de um run (polling)
  POST /api/runs/{run_id}/cancel -> para o run
  GET  /api/load-tools         -> tools do mix de carga (somente leitura) e limites
  POST /api/load-runs          -> dispara um teste de carga
  GET  /api/load-runs          -> lista cargas desta sessao do launcher
  GET  /api/load-runs/{id}     -> estado de uma carga (progresso ao vivo, polling)
  POST /api/load-runs/{id}/cancel -> para a carga e mata os servidores MCP
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
  - Um run por vez (de agente ou de carga, na mesma trava); timeout por query limitado.
  - Serving de /data confinado as raizes results/ e metrics/ (anti path traversal).
"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from tests.e2e.launcher.load_service import LoadRunService
from tests.e2e.launcher.providers import detect_providers, resolve_provider
from tests.e2e.launcher.run_gate import RunGate
from tests.e2e.launcher.service import RunAlreadyActiveError, RunService
from tests.e2e.load.engine import (
    DEFAULT_TIMEOUT_S,
    MAX_CONCURRENCY,
    MAX_DURATION_S,
    MAX_ITERATIONS,
    MAX_TIMEOUT_S,
    MIN_CONCURRENCY,
    MIN_DURATION_S,
    LoadConfig,
)
from tests.e2e.load.mix import ALLOWED_TOOLS, describe_catalog, validate_tools

__all__ = ["app", "create_app"]

# base_dir = tests/e2e/
_BASE_DIR = Path(__file__).resolve().parent.parent
_RESULTS_DIR = (_BASE_DIR / "results").resolve()
_METRICS_DIR = (_BASE_DIR / "metrics").resolve()
_DATA_ROOTS = {"results": _RESULTS_DIR, "metrics": _METRICS_DIR}
_FIXTURES_DIR = _BASE_DIR / "fixtures"

# Origens permitidas para o dev server do Vite (localhost apenas).
_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5174",
    "http://localhost:5174",
]


_ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
LAUNCHER_HEADER = "X-Launcher"
MAX_TIMEOUT_SECONDS = 1800


def _require_launcher_header(
    x_launcher: str | None = Header(default=None, alias=LAUNCHER_HEADER),
) -> None:
    if x_launcher != "1":
        raise HTTPException(status_code=403, detail=f"header {LAUNCHER_HEADER} ausente")


def _within(root: Path, target: Path) -> bool:
    # is_relative_to, nao startswith: "results2" passaria num prefixo de string.
    return target.is_relative_to(root)


class RunRequest(BaseModel):
    """Corpo de POST /api/runs."""

    provider: str | None = None  # "kiro-cli" | "claude" | None (auto)
    tags: list[str] | None = None  # esteira parcial
    case_id: str | None = None  # um unico caso (teste separado)
    # allow_inf_nan=False: inf/NaN fariam o deadline do runner nunca expirar.
    timeout_seconds: float | None = Field(
        default=None, gt=0, le=MAX_TIMEOUT_SECONDS, allow_inf_nan=False
    )


class LoadRunRequest(BaseModel):
    """Corpo de POST /api/load-runs. Campos desconhecidos são recusados."""

    model_config = ConfigDict(extra="forbid")

    concurrency: int = Field(ge=MIN_CONCURRENCY, le=MAX_CONCURRENCY)
    duration_seconds: float = Field(ge=MIN_DURATION_S, le=MAX_DURATION_S, allow_inf_nan=False)
    iterations: int | None = Field(default=None, ge=1, le=MAX_ITERATIONS)
    tools: list[str] | None = Field(default=None, min_length=1, max_length=len(ALLOWED_TOOLS))
    timeout_seconds: float | None = Field(
        default=None, gt=0, le=MAX_TIMEOUT_S, allow_inf_nan=False
    )

    @field_validator("tools")
    @classmethod
    def _only_read_only_tools(cls, tools: list[str] | None) -> list[str] | None:
        # Allow-list aqui, antes de qualquer processo: o body não escolhe o que o motor chama.
        return validate_tools(tools) if tools is not None else None

    def to_config(self) -> LoadConfig:
        return LoadConfig(
            concurrency=self.concurrency,
            duration_s=self.duration_seconds,
            iterations=self.iterations,
            tools=tuple(self.tools) if self.tools is not None else None,
            timeout_s=self.timeout_seconds if self.timeout_seconds is not None else DEFAULT_TIMEOUT_S,
        )


def create_app() -> FastAPI:
    app = FastAPI(
        title="<repositório anterior> E2E Launcher (dev)",
        description=(
            "Launcher de desenvolvimento que dispara os testes das tools MCP "
            "num provedor de IA (kiro-cli/claude). Nao e backend de producao."
        ),
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
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
    service = RunService(gate=gate)
    load_service = LoadRunService(gate=gate)

    # ---- meta ------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True}

    @app.get("/api/providers")
    def providers() -> dict[str, Any]:
        """Provedores detectados no PATH e qual seria o default (auto)."""
        infos = detect_providers()
        default = next((i.id for i in infos if i.installed), None)
        return {
            "providers": [
                {
                    "id": i.id,
                    "label": i.label,
                    "binary": i.binary,
                    "installed": i.installed,
                }
                for i in infos
            ],
            "default": default,
        }

    @app.get("/api/cases")
    def cases() -> dict[str, Any]:
        """Biblioteca de prompts: casos de teste disponiveis."""
        try:
            return {"cases": service.list_cases_meta()}
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ---- runs ------------------------------------------------------------

    @app.post("/api/runs", dependencies=[Depends(_require_launcher_header)])
    def start_run(req: RunRequest) -> dict[str, Any]:
        """Dispara uma bateria no provedor escolhido.

        - Esteira completa: body vazio (ou so provider).
        - Esteira parcial:  tags=[...].
        - Teste separado:   case_id="...".
        """
        try:
            provider = resolve_provider(req.provider)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            state = service.start_run(
                provider=provider,
                tags=req.tags,
                case_id=req.case_id,
                timeout_seconds=req.timeout_seconds,
            )
        except RunAlreadyActiveError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return state.to_dict()

    @app.get("/api/runs")
    def list_runs() -> dict[str, Any]:
        return {"runs": service.list()}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        state = service.get(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="run nao encontrado")
        return state.to_dict()

    @app.post("/api/runs/{run_id}/cancel", dependencies=[Depends(_require_launcher_header)])
    def cancel_run(run_id: str) -> dict[str, Any]:
        """Para o run: interrompe o caso em andamento e descarta os restantes.

        Idempotente: num run ja encerrado, devolve o estado sem mudar nada.
        """
        state = service.cancel(run_id)
        if state is None:
            raise HTTPException(status_code=404, detail="run nao encontrado")
        return state.to_dict()

    # ---- cargas ----------------------------------------------------------

    @app.get("/api/load-tools")
    def load_tools() -> dict[str, Any]:
        """Tools do mix de carga (só leitura), se há fonte para elas, e os limites aceitos."""
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
        """Dispara um teste de carga; 409 se qualquer outro run estiver ativo."""
        try:
            state = load_service.start_run(req.to_config())
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
        files = [
            p.name
            for p in root.iterdir()
            if p.is_file() and p.suffix in (".json", ".jsonl")
        ]
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
