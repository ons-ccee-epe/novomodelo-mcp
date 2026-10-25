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
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any
from urllib.parse import urlsplit

from ..names import BINDING_DIST, BRIDGE_CLI, BRIDGE_DIST, MCP_DIST
from .discovery import bridge_origin, bridge_version

CLI_RELEASES = "https://github.com/ons-ccee-epe/novomodelo/releases"
NOVOMODELO_LATEST = "https://api.github.com/repos/ons-ccee-epe/novomodelo/releases/latest"
BRIDGE_PYPI = "https://pypi.org/pypi/novomodelo-bridge/json"
BRIDGE_RELEASES = "https://github.com/ons-ccee-epe/novomodelo-bridge/releases"
BRIDGE_LATEST = "https://api.github.com/repos/ons-ccee-epe/novomodelo-bridge/releases/latest"
BRIDGE_PAGE = "https://pypi.org/project/novomodelo-bridge/"
UPDATE_BUDGET_S = 3.0
UPDATE_TTL_S = 6 * 3600
NOTES_MAX_LINES = 6
NOTES_MAX_LINE_CHARS = 200
NOTES_MAX_CHARS = 1200
_NOTES_SECTIONS = ("changed", "fixed")
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
    """O pin exato do bridge nos metadados do próprio pacote do MCP.

    O bridge fixa a mesma versão da biblioteca, então o pin dele vale para as duas.
    Não é a versão do MCP: o pacote só passa a ter a versão do novomodelo no release.
    """
    try:
        requirements = metadata.requires(MCP_DIST) or []
    except metadata.PackageNotFoundError:
        return None
    for req in requirements:
        if m := re.match(rf"^{re.escape(BRIDGE_DIST)}\s*==\s*([^;\s,]+)", req):
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
    bridge = bridge_version(bridge_path, origin)
    return {
        "executavel": _piece(cli.get("version") if cli.get("status") == "ok" else None,
                             "não encontrado"),
        "biblioteca": _piece(lib, "não encontrada no ambiente do MCP"),
        "bridge": _piece(bridge.split()[-1] if bridge else None, "não encontrado")
        | {"origem": origin},
        "docs": _docs_piece(),
    }


def _docs_piece() -> dict[str, Any]:
    from .reference import bundled_manifest
    manifest = bundled_manifest()
    if not manifest:
        return {"versao": None, "motivo": "sem manifesto"}
    return _piece(manifest.get("docs_versao"), "manifesto sem versão") | {
        "commit": manifest.get("docs_commit")}


@functools.lru_cache(maxsize=8)
def local_versions(settings) -> dict[str, dict[str, Any]]:
    return _read_local(settings)


def cli_install_command(version: str) -> str:
    base = f"{CLI_RELEASES}/download/v{version}"
    if sys.platform == "win32":
        return (f'powershell -ExecutionPolicy Bypass -c "irm {base}/novomodelo-cli-installer.ps1'
                ' | iex"')
    return f"curl --proto '=https' --tlsv1.2 -LsSf {base}/novomodelo-cli-installer.sh | sh"


MCP_UPGRADE_COMMAND = f"uv tool upgrade {MCP_DIST}"
ASK_AGENT_TO_INSTALL = ("Peça ao agente: “instale o executável do novomodelo” "
                        "(tool instalar_novomodelo)")


def mcp_install_command(version: str) -> str:
    return f"uv tool install --force --compile-bytecode {MCP_DIST}=={version}"


def _bridge_command(version: str, origin: str | None = None) -> str:
    if origin == "pacote":
        return mcp_install_command(version)
    return f"uv tool install --force {BRIDGE_CLI}=={version}"


def _newer_piece_warning(label: str, version: str, expected: str, align: str) -> str:
    name = label[0].upper() + label[1:]
    verb = "estão" if label.startswith("as ") else "está"
    return (f"{name} {verb} na {version} e o MCP na {expected}; o MCP foi testado com as peças "
            f"na versão dele. Para alinhar, atualize o MCP ({MCP_UPGRADE_COMMAND}), se já houver "
            f"o MCP {version}, ou volte {label} para a {expected}: {align}.")


def _piece_warnings(settings, expected: str) -> list[str]:
    """Avisos com a versão do MCP como referência, cada um com os comandos para alinhar.

    A peça mais velha sobe até a versão do MCP. Para a mais nova há dois caminhos, porque
    sem rede o MCP não sabe se já saiu o MCP da versão dela: atualizar o MCP ou voltar a
    peça para a versão do MCP.
    """
    pieces = local_versions(settings)
    actions = {
        "executavel": ("o executável novomodelo",
                       f"{ASK_AGENT_TO_INSTALL}. Manual: {cli_install_command(expected)}"),
        "biblioteca": ("a biblioteca novomodelo-python", mcp_install_command(expected)),
        "bridge": (f"o {BRIDGE_CLI}", _bridge_command(expected, pieces["bridge"].get("origem"))),
        "docs": ("as docs embutidas", mcp_install_command(expected)),
    }
    lines = []
    for key, (label, action) in actions.items():
        version = normalize_version(pieces[key]["versao"])
        verb = "" if key == "executavel" else "Instale: "
        name = label.split(" ", 1)[1]
        if version is not None and not _version_key(version):
            continue
        if version is None:
            if key != "docs":
                lines.append(f"{name} {pieces[key]['motivo']}. {verb}{action}")
        elif _version_key(version) < _version_key(expected):
            verb = "" if key == "executavel" else "Atualize: "
            lines.append(f"{name} na versão {version}; a do MCP é {expected}. {verb}{action}")
        elif _version_key(version) > _version_key(expected):
            notes = {"executavel": ("novomodelo", CLI_RELEASES),
                     "bridge": ("bridge", BRIDGE_RELEASES)}.get(key)
            lines.append(_newer_piece_warning(label, version, expected, action)
                         + (_notes_text(notes[0], version, notes[1]) if notes else ""))
    return lines


def version_warnings(settings) -> list[str]:
    """Uma linha por peça ausente ou de outra versão, com o comando para corrigir; e o
    aviso de docs lidas de uma pasta de desenvolvimento."""
    from .reference import docs_origin
    expected = expected_version()
    lines = _piece_warnings(settings, expected) if expected else []
    origin = docs_origin(settings)
    if origin["origem"] == "pasta_de_desenvolvimento":
        lines.append(f"docs lidas de uma pasta de desenvolvimento ({origin['caminho']}), não "
                     "das embutidas da versão do MCP; tire NOVOMODELO_MCP_DOCS_DIR da "
                     "configuração para usar as embutidas")
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


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(" ", 1)[0] + "…"


def release_changes(body: str | None) -> list[str]:
    """As linhas de "Changed" e "Fixed" das notas do release, as BREAKING primeiro.

    Cada item vira uma linha (as continuações são juntadas), sem o negrito do markdown,
    com teto de linhas e de caracteres; o que sobra vira "(mais N nas notas)".
    """
    items: list[str] = []
    section = None
    for raw in (body or "").splitlines():
        line = raw.strip()
        if heading := re.match(r"^#+\s*(.+)$", line):
            section = heading.group(1).strip().lower()
            continue
        if section not in _NOTES_SECTIONS or not line:
            continue
        if re.match(r"^[-*]\s+", raw):
            items.append(re.sub(r"^[-*]\s+", "", line))
        elif items:
            items[-1] += " " + line
    items = [i.replace("**", "") for i in items]
    items.sort(key=lambda i: "BREAKING" not in i)
    lines: list[str] = []
    for item in items:
        line = _shorten(item, NOTES_MAX_LINE_CHARS)
        if len(lines) == NOTES_MAX_LINES or sum(map(len, lines)) + len(line) > NOTES_MAX_CHARS:
            break
        lines.append(line)
    if len(lines) < len(items):
        lines.append(f"(mais {len(items) - len(lines)} nas notas)")
    return lines


def _release_notes(fetched: dict[str, Any], version: str, releases: str) -> dict[str, Any]:
    """`notas` (o link) e, se o release lido é o da `version`, `mudancas`."""
    data = fetched.get("dados") if isinstance(fetched, dict) else None
    if isinstance(data, dict) and normalize_version(data.get("tag_name")) == version:
        changes = release_changes(data.get("body"))
        link = data.get("html_url") or f"{releases}/tag/v{version}"
        return {"notas": link, **({"mudancas": changes} if changes else {})}
    return {"notas": f"{releases}/tag/v{version}"}


def _cached_notes(piece: str, version: str) -> dict[str, Any] | None:
    if "resultado" not in _UPDATE or time.monotonic() - _UPDATE["quando"] >= UPDATE_TTL_S:
        return None
    notes = _UPDATE.get("notas", {}).get(piece)
    return notes if notes and notes.get("versao") == version else None


def _notes_text(piece: str, version: str, releases: str) -> str:
    notes = _cached_notes(piece, version)
    if notes and notes.get("mudancas"):
        bullets = "".join(f"\n- {line}" for line in notes["mudancas"])
        return f" Mudanças da {version}:{bullets}\nNotas: {notes['notas']}"
    link = notes["notas"] if notes else f"{releases}/tag/v{version}"
    return f" Notas da {version}: {link}"


def _release_note(piece: str, newest: str, current: str | None) -> str:
    return (f"o {piece} {newest} saiu; o MCP está na {current}. Quando sair o MCP {newest}, "
            f"atualize as peças juntas: {MCP_UPGRADE_COMMAND}.")


def update_check(settings, *, budget_s: float = UPDATE_BUDGET_S) -> dict[str, Any]:
    """Há versão nova do novomodelo, do bridge e do MCP? Consulta no máximo uma vez a
    cada `UPDATE_TTL_S`: um cliente aberto há horas também vê um lançamento.

    Um novomodelo novo não garante o MCP da mesma versão, então nenhuma peça nova vem
    com comando próprio (instalar só uma peça desalinha as outras); a nota diz como
    atualizar o MCP, que traz as peças juntas. Todo o trabalho cabe em `budget_s`; o que não responder a tempo vira aviso.
    """
    if "resultado" in _UPDATE and time.monotonic() - _UPDATE["quando"] < UPDATE_TTL_S:
        return _UPDATE["resultado"]
    pieces = local_versions(settings)
    current = expected_version() or pieces["executavel"]["versao"]
    origin = pieces["bridge"].get("origem")
    pool = ThreadPoolExecutor(max_workers=3)
    futures = {"novomodelo": pool.submit(fetch_json, NOVOMODELO_LATEST, timeout=budget_s),
               "bridge": pool.submit(fetch_json, BRIDGE_PYPI, timeout=budget_s),
               "bridge_notas": pool.submit(fetch_json, BRIDGE_LATEST, timeout=budget_s)}
    wait(futures.values(), timeout=budget_s)
    pool.shutdown(wait=False, cancel_futures=True)
    late = {"aviso_rede": f"tempo esgotado ({budget_s:g} s)"}
    got = {k: (f.result() if f.done() else late) for k, f in futures.items()}
    cli = _newer(current, got["novomodelo"], lambda d: d["tag_name"], CLI_RELEASES,
                 cli_install_command)
    bridge = _newer(current, got["bridge"], lambda d: d["info"]["version"], BRIDGE_PAGE,
                    lambda v: _bridge_command(v, origin))
    notes: dict[str, dict[str, Any]] = {}
    if cli.get("mais_recente"):
        notes["novomodelo"] = {"versao": cli["mais_recente"], **_release_notes(
            got["novomodelo"], cli["mais_recente"], CLI_RELEASES)}
    if bridge.get("mais_recente"):
        notes["bridge"] = {"versao": bridge["mais_recente"], **_release_notes(
            got["bridge_notas"], bridge["mais_recente"], BRIDGE_RELEASES)}
    if cli["status"] == "nova":
        newest = cli["mais_recente"]
        note = _release_note("novomodelo", newest, current)
        cli = {k: v for k, v in cli.items() if k != "comando"} | {"nota": note} | {
            k: v for k, v in notes["novomodelo"].items() if k != "versao"}
        mcp = {"status": "a_conferir", "novomodelo": newest, "nota": note}
    else:
        mcp = {"status": cli["status"], "nota": "inferida pela versão do novomodelo"}
    if bridge["status"] == "nova":
        bridge = {k: v for k, v in bridge.items() if k != "comando"} | {
            "nota": _release_note(BRIDGE_CLI, bridge["mais_recente"], current)} | {
            k: v for k, v in notes["bridge"].items() if k != "versao"}
    _UPDATE["resultado"] = {"novomodelo": cli, "bridge": bridge, "mcp": mcp}
    _UPDATE["notas"] = notes
    _UPDATE["quando"] = time.monotonic()
    return _UPDATE["resultado"]


def reset_caches() -> None:
    local_versions.cache_clear()
    _UPDATE.clear()
