"""Versões das peças (executável, biblioteca, bridge, docs) e a verificação de versão nova.

Dono único da comparação de versões (nenhuma tool compara por conta própria) e da
única saída de rede do MCP (`fetch_bytes`/`fetch_json`): só domínios oficiais, timeout
curto, certificados do sistema por um contexto local do `truststore`. Nunca levanta:
falha vira `aviso_rede`.
"""
from __future__ import annotations

import functools
import importlib.metadata as metadata
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any
from urllib.parse import urlsplit

from ..names import BINDING_DIST, BRIDGE_CLI, MCP_DIST, MCP_RELEASE_TAG_URL
from .discovery import bridge_origin, tool_version

CLI_RELEASES = "https://github.com/ons-ccee-epe/novomodelo/releases"
NOVOMODELO_LATEST = "https://api.github.com/repos/ons-ccee-epe/novomodelo/releases/latest"
BRIDGE_PYPI = "https://pypi.org/pypi/novomodelo-bridge/json"
BRIDGE_PAGE = "https://pypi.org/project/novomodelo-bridge/"
UPDATE_BUDGET_S = 3.0
_MAX_BYTES = 64 * 1024 * 1024

#: (host, prefixo de caminho) permitidos; o CDN do GitHub só como destino de redirecionamento.
_ALLOWED = (("github.com", "/ons-ccee-epe/"), ("api.github.com", "/repos/ons-ccee-epe/"),
            ("pypi.org", "/pypi/novomodelo-bridge/"))
_REDIRECT_ONLY = ("release-assets.githubusercontent.com",)


# ── versões ───────────────────────────────────────────────────────────────────

def normalize_version(version: Any) -> str | None:
    """`"v0.18.0"`, `"0.18.0.post2"` → `"0.18.0"`; vazio ou None → None."""
    text = re.sub(r"\.post\d+$", "", str(version or "").strip().lstrip("vV"))
    return text or None


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def expected_version() -> str | None:
    """O pin exato da biblioteca nos metadados do próprio pacote do MCP.

    Não é a versão do MCP: o pacote só passa a ter a versão do novomodelo no release.
    """
    try:
        requirements = metadata.requires(MCP_DIST) or []
    except metadata.PackageNotFoundError:
        return None
    for req in requirements:
        if m := re.match(rf"^{re.escape(BINDING_DIST)}\s*==\s*([^;\s,]+)", req):
            return normalize_version(m.group(1))
    return None


def _piece(version: Any, missing: str) -> dict[str, Any]:
    v = normalize_version(version)
    return {"versao": v} if v else {"versao": None, "motivo": missing}


def _read_local(settings) -> dict[str, dict[str, Any]]:
    from .novomodelo import version_cli
    cli = version_cli(settings=settings)
    try:
        lib = metadata.version(BINDING_DIST)
    except metadata.PackageNotFoundError:
        lib = None
    bridge_path, origin = bridge_origin(settings)
    if origin == "pacote":
        bridge = metadata.version(BRIDGE_CLI)
    else:
        bridge = tool_version(bridge_path)
    return {
        "executavel": _piece(cli.get("version") if cli.get("status") == "ok" else None,
                             "não encontrado"),
        "biblioteca": _piece(lib, "não encontrada no ambiente do MCP"),
        "bridge": _piece(bridge.split()[-1] if bridge else None, "não encontrado")
        | {"origem": origin},
        "docs": {"versao": None, "motivo": "sem manifesto"},
    }


@functools.lru_cache(maxsize=8)
def local_versions(settings) -> dict[str, dict[str, Any]]:
    return _read_local(settings)


def cli_install_command(version: str) -> str:
    base = f"{CLI_RELEASES}/download/v{version}"
    if sys.platform == "win32":
        return (f'powershell -ExecutionPolicy Bypass -c "irm {base}/novomodelo-cli-installer.ps1'
                ' | iex"')
    return f"curl --proto '=https' --tlsv1.2 -LsSf {base}/novomodelo-cli-installer.sh | sh"


def _bridge_command(version: str, origin: str | None = None) -> str:
    if origin == "pacote":
        return f"reinstale o MCP {version} (o bridge vem junto)"
    return f"uv tool install --force {BRIDGE_CLI}=={version}"


def version_warnings(settings) -> list[str]:
    """Uma linha por peça ausente ou de outra versão, com o comando para corrigir."""
    expected = expected_version()
    if not expected:
        return []
    pieces = local_versions(settings)
    lines = []
    texts = {
        "executavel": ("executável novomodelo", cli_install_command(expected)),
        "biblioteca": ("biblioteca novomodelo-python",
                       f"reinstale o MCP {expected} (a biblioteca vem junto)"),
        "bridge": (BRIDGE_CLI, _bridge_command(expected, pieces["bridge"].get("origem"))),
    }
    for key, (label, command) in texts.items():
        found = normalize_version(pieces[key]["versao"])
        if found is None:
            lines.append(f"{label} {pieces[key]['motivo']}. Instale: {command}")
        elif found != expected:
            lines.append(f"{label} na versão {found}; o MCP espera {expected}. "
                         f"Atualize: {command}")
    return lines


# ── rede ──────────────────────────────────────────────────────────────────────

def allowed_url(url: str, *, redirect: bool = False) -> bool:
    parts = urlsplit(url)
    if parts.scheme != "https":
        return False
    host, path = (parts.hostname or "").lower(), parts.path or "/"
    if redirect and host in _REDIRECT_ONLY:
        return True
    return any(host == h and path.startswith(p) for h, p in _ALLOWED)


def _ssl_context() -> ssl.SSLContext:
    # contexto local, nunca truststore.inject_into_ssl(): injetar troca o SSL do
    # processo inteiro (FastMCP, DuckDB, o próprio bridge em processo).
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 - sem truststore (ou falha ao carregá-lo): contexto padrão
        return ssl.create_default_context()


class _AllowlistRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl, redirect=True):
            raise urllib.error.URLError(
                f"redirecionamento para domínio não permitido: {urlsplit(newurl).hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(req: urllib.request.Request, *, timeout: float, context: ssl.SSLContext) -> bytes:
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context),
                                         _AllowlistRedirect())
    with opener.open(req, timeout=timeout) as resp:
        return resp.read(_MAX_BYTES)


def _is_cert_error(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, ssl.SSLError) or "CERTIFICATE" in str(reason).upper()


def _reason(exc: BaseException) -> str:
    if _is_cert_error(exc):
        return f"falha de certificado ({getattr(exc, 'reason', exc)})"
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, TimeoutError) or "timed out" in str(exc):
        return "tempo esgotado"
    return f"sem conexão ({getattr(exc, 'reason', exc)})"


def fetch_bytes(url: str, *, timeout: float) -> bytes | dict[str, str]:
    """Conteúdo de `url` ou `{"aviso_rede": motivo}`; nunca levanta."""
    host = urlsplit(url).hostname or url
    if not allowed_url(url):
        return {"aviso_rede": f"domínio não permitido: {host}"}
    req = urllib.request.Request(url, headers={"User-Agent": MCP_DIST})
    context = _ssl_context()
    try:
        try:
            return _open(req, timeout=timeout, context=context)
        except (urllib.error.URLError, ssl.SSLError) as exc:
            if not _is_cert_error(exc) or type(context) is ssl.SSLContext:
                raise
            return _open(req, timeout=timeout, context=ssl.create_default_context())
    except Exception as exc:  # noqa: BLE001 - never-raise: rede indisponível vira aviso, não derruba a tool
        return {"aviso_rede": f"não foi possível acessar {host}: {_reason(exc)}"}


def fetch_json(url: str, *, timeout: float) -> dict[str, Any]:
    body = fetch_bytes(url, timeout=timeout)
    if isinstance(body, dict):
        return body
    try:
        return {"dados": json.loads(body)}
    except ValueError:
        return {"aviso_rede": f"resposta não é JSON: {urlsplit(url).hostname}"}


# ── versão nova (server_info) ─────────────────────────────────────────────────

_UPDATE: dict[str, Any] = {}


def _newer(current: str | None, fetched: dict[str, Any], extract, manual: str,
           command) -> dict[str, Any]:
    if "aviso_rede" in fetched:
        return {"status": "nao_foi_possivel_verificar", "aviso_rede": fetched["aviso_rede"],
                "verifique_em": manual}
    try:
        latest = normalize_version(extract(fetched["dados"]))
    except (KeyError, TypeError):
        latest = None
    if not latest:
        return {"status": "nao_foi_possivel_verificar", "aviso_rede": "resposta sem versão",
                "verifique_em": manual}
    if current and _version_key(latest) <= _version_key(current):
        return {"status": "atual", "mais_recente": latest}
    return {"status": "nova", "mais_recente": latest, "comando": command(latest)}


def update_check(settings, *, budget_s: float = UPDATE_BUDGET_S) -> dict[str, Any]:
    """Uma vez por processo: há versão nova do novomodelo, do bridge e do MCP?

    O MCP é inferido pelo novomodelo (o repositório do MCP é privado). Todo o
    trabalho cabe em `budget_s`; o que não responder a tempo vira aviso.
    """
    if "resultado" in _UPDATE:
        return _UPDATE["resultado"]
    pieces = local_versions(settings)
    current = expected_version() or pieces["executavel"]["versao"]
    origin = pieces["bridge"].get("origem")
    pool = ThreadPoolExecutor(max_workers=2)
    futures = {"novomodelo": pool.submit(fetch_json, NOVOMODELO_LATEST, timeout=budget_s),
               "bridge": pool.submit(fetch_json, BRIDGE_PYPI, timeout=budget_s)}
    wait(futures.values(), timeout=budget_s)
    pool.shutdown(wait=False, cancel_futures=True)
    late = {"aviso_rede": f"tempo esgotado ({budget_s:g} s)"}
    got = {k: (f.result() if f.done() else late) for k, f in futures.items()}
    cli = _newer(current, got["novomodelo"], lambda d: d["tag_name"], CLI_RELEASES,
                 cli_install_command)
    bridge = _newer(current, got["bridge"], lambda d: d["info"]["version"], BRIDGE_PAGE,
                    lambda v: _bridge_command(v, origin))
    if cli["status"] == "nova":
        mcp = {"status": "nova", "mais_recente": cli["mais_recente"],
               "link": f"{MCP_RELEASE_TAG_URL}v{cli['mais_recente']}",
               "nota": "inferida pela versão do novomodelo; atualize as três peças juntas, "
                       "na mesma versão"}
    else:
        mcp = {"status": cli["status"], "nota": "inferida pela versão do novomodelo"}
    _UPDATE["resultado"] = {"novomodelo": cli, "bridge": bridge, "mcp": mcp}
    return _UPDATE["resultado"]


def reset_caches() -> None:
    local_versions.cache_clear()
    _UPDATE.clear()
