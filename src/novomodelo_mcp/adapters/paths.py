"""Guard de caminho: confina leitura/escrita às raízes permitidas.

Modelo de ameaça: um agente de IA controla os caminhos passados às tools. Mesmo
offline, o servidor lê/escreve com os privilégios do usuário. Este guard trata a
entrada como não confiável.

- Raízes: `NOVOMODELO_MCP_WORKSPACE` (separadas por os.pathsep) mais as pastas que o
  usuário aprovou em `incluir_pastas` (`pastas.json` no state dir, relido a cada chamada).
- Sem `NOVOMODELO_MCP_WORKSPACE`: opera irrestrito (o `server_info` sinaliza isso).
- Com raiz(es): qualquer caminho fora delas é RECUSADO (fail-closed). `resolve()`
  neutraliza symlinks e `..`. `pastas.json` ilegível vale como lista vazia, nunca
  como liberação.
- A recusa diz ao agente para não contornar e para pedir ao usuário a inclusão.
"""

from __future__ import annotations

import inspect
import json
import os
import re
from pathlib import Path
from typing import Any

from ..config import Settings
from .envelope import error
from .state import atomic_write_text, default_state_dir, file_lock

NAO_CONTORNE = (
    "Caminho fora da pasta de trabalho: não leia esse caminho por outras ferramentas "
    "(leitura de arquivo, terminal, outro MCP). Pergunte ao usuário se pode incluir a "
    "pasta (`pasta_sugerida` da recusa); com o sim, chame `incluir_pastas` com todas as "
    "pastas de uma vez e tente de novo. Não peça ao usuário para rodar comandos."
)

AVISO_NA_TOOL = (
    "Caminho fora da pasta de trabalho é recusado: não contorne com outras ferramentas; "
    "pergunte ao usuário e inclua a pasta com `incluir_pastas`."
)

#: Parâmetros de tool que recebem caminho e passam pelo guard.
PATH_PARAMS = frozenset(
    {
        "path",
        "case_dir",
        "src",
        "dst",
        "output_dir",
        "out_dir",
        "output",
        "directory",
        "newave_dir",
        "decomp_dir",
    }
)

#: Tools guardadas cujo caminho vem dentro de outro parâmetro (o SQL do `deck_sql`).
GUARDED_WITHOUT_PATH_PARAM = frozenset({"deck_sql"})

#: Pastas do HOME que guardam configuração e credenciais de programas.
_CONFIG_DIRS = frozenset({"appdata", "library"})

_PASTAS_FILE = "pastas.json"


def _resolve_all(parts: list[str]) -> list[Path]:
    roots: list[Path] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            roots.append(Path(part).expanduser().resolve())
        except OSError:
            continue
    return roots


def _state_root(settings: Settings) -> Path:
    # Sem `state_dir()`: ele cria a pasta, e o guard roda em toda chamada.
    return Path(settings.state_dir).expanduser() if settings.state_dir else default_state_dir()


def _pastas_path(settings: Settings) -> Path:
    return _state_root(settings) / _PASTAS_FILE


def included_roots(settings: Settings) -> list[Path]:
    """As pastas aprovadas em `incluir_pastas`; arquivo ausente ou ilegível → []."""
    try:
        data = json.loads(_pastas_path(settings).read_text(encoding="utf-8"))
        pastas = data["pastas"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    return _resolve_all([p for p in pastas if isinstance(p, str)])


def configured_roots(settings: Settings) -> list[Path]:
    return _resolve_all((settings.workspace or "").split(os.pathsep))


def allowed_roots(settings: Settings) -> list[Path]:
    configured = configured_roots(settings)
    if not configured:
        return []
    extra = [r for r in included_roots(settings) if r not in configured]
    return [*configured, *extra]


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def suggested_folder(resolved: Path) -> Path:
    return resolved if resolved.is_dir() else resolved.parent


def refuse_outside(text: str, resolved: Path, roots: list[Path]) -> dict[str, Any]:
    """Envelope 13 de caminho fora das raízes, com a instrução de não contornar."""
    env = error(
        13,
        f"caminho fora do workspace permitido: {text}",
        pasta_sugerida=str(suggested_folder(resolved)),
    )
    env["diagnostics"] += [NAO_CONTORNE, f"raizes: {[str(r) for r in roots]}"]
    return env


#: Esquema de URL (`http://`, `s3://`, `hf://`); dois caracteres ou mais, para não
#: confundir com a letra de unidade do Windows (`C:/`).
_URL = re.compile(r"^\s*[A-Za-z][A-Za-z0-9+.\-]+://")


def ensure_in_workspace(*paths: str | None, settings: Settings) -> dict | None:
    """None se todos os caminhos estão dentro da raiz (ou se não há raiz);
    senão, um envelope de erro. Chamada no topo de toda tool que recebe caminho.
    """
    for p in paths:
        if p is not None and _URL.match(p):
            # Vale também sem workspace: polars e DuckDB leem URL, e a única saída de
            # rede do MCP é a checagem de versões.
            return error(22, f"caminho invalido: {p}", "o MCP só lê arquivos locais, não URL")
    roots = allowed_roots(settings)
    if not roots:
        return None  # irrestrito
    for p in paths:
        if p is None:
            continue
        try:
            rp = Path(p).expanduser().resolve()
        except (OSError, ValueError) as exc:
            return error(22, f"caminho invalido: {p!r}", str(exc))
        if not any(_within(rp, root) for root in roots):
            return refuse_outside(p, rp, roots)
    return None


def forbidden_reason(folder: Path, settings: Settings) -> str | None:
    """Por que `folder` (já resolvida) não pode virar raiz; None se pode."""
    home = Path.home().resolve()
    state = _state_root(settings).resolve()
    if not folder.is_dir():
        return "não é uma pasta existente"
    if folder == Path(folder.anchor):
        return "raiz do disco"
    if _within(home, folder):
        return "a pasta pessoal inteira (ou acima dela); escolha a pasta dos estudos"
    if _within(folder, home):
        first = folder.relative_to(home).parts[0]
        if first.startswith(".") or first.lower() in _CONFIG_DIRS:
            return "pasta de configuração de programas"
    if _within(folder, state) or _within(state, folder):
        return "pasta de estado do MCP"
    return None


def include_folders(pastas: list[str], settings: Settings) -> dict[str, Any]:
    """Acrescenta pastas às raízes (em `pastas.json`); cada pasta é aceita ou recusada com motivo."""
    if not pastas:
        return error(22, "informe ao menos uma pasta em `pastas`")
    if not configured_roots(settings):
        return {
            "status": "ok",
            "incluidas": [],
            "aviso": "sem pasta de trabalho definida "
            "(NOVOMODELO_MCP_WORKSPACE): todas as pastas já são aceitas; nada foi gravado",
        }
    roots = allowed_roots(settings)
    incluidas, ja, recusadas = [], [], []
    for texto in pastas:
        try:
            folder = Path(texto).expanduser().resolve()
        except OSError as exc:
            recusadas.append({"pasta": texto, "motivo": f"caminho inválido ({exc})"})
            continue
        if any(_within(folder, r) for r in roots):
            ja.append(str(folder))
        elif motivo := forbidden_reason(folder, settings):
            recusadas.append({"pasta": texto, "motivo": motivo})
        elif str(folder) not in incluidas:
            incluidas.append(str(folder))
    if incluidas:
        path = _pastas_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        with file_lock(path.with_name(f"{_PASTAS_FILE}.lock")):
            atuais = [str(r) for r in included_roots(settings)]
            novas = atuais + [p for p in incluidas if p not in atuais]
            atomic_write_text(path, json.dumps({"pastas": novas}, indent=2, ensure_ascii=False))
    raizes = [str(r) for r in allowed_roots(settings)]
    if not incluidas and not ja:
        return error(22, "nenhuma pasta foi incluída", recusadas=recusadas, raizes=raizes)
    return {
        "status": "ok",
        "incluidas": incluidas,
        "ja_incluidas": ja,
        "recusadas": recusadas,
        "raizes": raizes,
    }


def is_guarded_tool(fn: Any) -> bool:
    """A tool recebe caminho (pelos nomes de `PATH_PARAMS`) ou está em `GUARDED_WITHOUT_PATH_PARAM`."""
    params = set(inspect.signature(fn).parameters)
    return bool(params & PATH_PARAMS) or fn.__name__ in GUARDED_WITHOUT_PATH_PARAM
