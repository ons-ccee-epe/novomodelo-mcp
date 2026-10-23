"""`novomodelo-mcp configurar`: grava a entrada do MCP na configuração do cliente.

Altera só a chave `novomodelo` (e a lista de liberação das tools de leitura, onde o
cliente aceita uma); o resto do arquivo é preservado. A pasta de trabalho nunca tem
padrão: vem de `--workspace`, da pergunta no terminal, ou é recusada de propósito com
`--irrestrito`. Antes de gravar faz backup
`<arquivo>.bak-AAAAMMDD-HHMMSS`; grava de forma atômica e relê o JSON.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import sysconfig
from pathlib import Path
from typing import Any

from .names import ENV_PREFIX, MCP_DIST, SERVER_NAME

CLIENTS = ("claude-desktop", "claude-code", "kiro")
CLIENT_NAMES = {"claude-desktop": "Claude Desktop", "claude-code": "Claude Code", "kiro": "Kiro"}
SYSTEM_APPS = Path("/Applications")
_PROGRAMS = {"claude-desktop": (), "claude-code": ("claude",), "kiro": ("kiro", "kiro-cli")}
INSTRUCTIONS_MARK = "<!-- novomodelo-mcp -->"
INSTRUCTIONS_LINE = (
    "Para perguntas sobre a metodologia do novomodelo, use o MCP novomodelo: "
    "`docs_search` (em inglês) e `docs_read`, citando `pagina#secao`."
)


class ConfigError(Exception):
    """Arquivo do cliente ilegível: nada é gravado."""


def read_only_tools() -> list[str]:
    """As tools com `readOnlyHint=True` do servidor montado (fonte única)."""
    from .server import build_server
    return sorted(t.name for t in build_server()._tool_manager.list_tools()
                  if t.annotations and t.annotations.readOnlyHint)


def server_command() -> tuple[str, list[str]]:
    """Caminho absoluto do executável deste pacote, e os argumentos.

    Procura no diretório de scripts do próprio interpretador, nunca no PATH: o release
    do novomodelo publica outro `novomodelo-mcp` (Rust), e o primeiro do PATH venceria.
    """
    own = shutil.which(MCP_DIST, path=sysconfig.get_path("scripts"))
    if own:
        return str(Path(own).absolute()), []
    return str(Path(sys.executable).absolute()), ["-m", "novomodelo_mcp"]


def _home() -> Path:
    return Path.home()


def config_path(client: str) -> Path:
    home = _home()
    if client == "claude-code":
        return home / ".claude.json"
    if client == "kiro":
        return home / ".kiro" / "settings" / "mcp.json"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def _install_paths(client: str) -> list[Path]:
    home = _home()
    if client == "claude-code":
        return [home / ".claude" / "local" / "claude"]
    if sys.platform == "darwin":
        app = {"claude-desktop": "Claude.app", "kiro": "Kiro.app"}[client]
        return [SYSTEM_APPS / app, home / "Applications" / app]
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        if client == "claude-desktop":
            return [local / "AnthropicClaude", local / "Programs" / "Claude"]
        return [local / "Programs" / "Kiro"]
    return []


def _config_dir(client: str) -> Path:
    return {"claude-code": _home() / ".claude", "kiro": _home() / ".kiro"}.get(
        client, config_path(client).parent)


def client_found(client: str) -> bool:
    """O programa (no PATH ou no lugar de instalação) ou a pasta de configuração existe."""
    return (any(shutil.which(name) for name in _PROGRAMS[client])
            or any(p.exists() for p in [*_install_paths(client), _config_dir(client)]))


def server_entry(client: str, workspace: list[str]) -> dict[str, Any]:
    command, args = server_command()
    entry: dict[str, Any] = {"type": "stdio"} if client == "claude-code" else {}
    entry.update(command=command, args=args, env={})
    if workspace:
        roots = (str(Path(w).expanduser().resolve()) for w in workspace)
        entry["env"][f"{ENV_PREFIX}WORKSPACE"] = os.pathsep.join(roots)
    if client == "kiro":
        entry["autoApprove"] = read_only_tools()
    return entry


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{path} não é um JSON válido ({exc}); corrija ou mova o "
                          "arquivo e rode de novo. Nada foi gravado.") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} não contém um objeto JSON. Nada foi gravado.")
    return data


def _with_server(data: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
    return {**data, "mcpServers": {**servers, SERVER_NAME: entry}}


def allow_rules(tools: list[str]) -> list[str]:
    # Uma a uma, nunca `mcp__novomodelo__*`: o curinga liberaria também as que gravam.
    return [f"mcp__{SERVER_NAME}__{t}" for t in tools]


def _with_allow(data: dict[str, Any], rules: list[str]) -> dict[str, Any]:
    perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
    allow = list(perms.get("allow") or [])
    allow += [r for r in rules if r not in allow]
    return {**data, "permissions": {**perms, "allow": allow}}


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _instructions_change(client: str) -> tuple[Path, str] | None:
    home = _home()
    if client == "claude-code":
        path = home / ".claude" / "CLAUDE.md"
        current = path.read_bytes().decode("utf-8") if path.exists() else ""
        if INSTRUCTIONS_MARK in current:
            return path, current
        sep = "" if not current or current.endswith("\n\n") else (
            "\n" if current.endswith("\n") else "\n\n")
        return path, f"{current}{sep}{INSTRUCTIONS_MARK}\n{INSTRUCTIONS_LINE}\n"
    if client == "kiro":
        path = home / ".kiro" / "steering" / "novomodelo.md"
        return path, f"---\ninclusion: always\n---\n\n{INSTRUCTIONS_LINE}\n"
    return None


def plan(client: str, workspace: list[str], instructions: bool) -> list[tuple[Path, str, str]]:
    """(arquivo, conteúdo novo, trecho que muda) de cada arquivo; levanta `ConfigError`
    sem gravar nada. O trecho é o que `--mostrar` imprime: o arquivo inteiro do cliente
    pode trazer histórico e dados de outros servidores."""
    entry = server_entry(client, workspace)
    path = config_path(client)
    changes = [(path, _dump(_with_server(_load(path), entry)),
                _dump({"mcpServers": {SERVER_NAME: entry}}))]
    if client == "claude-code":
        settings = _home() / ".claude" / "settings.json"
        rules = allow_rules(read_only_tools())
        changes.append((settings, _dump(_with_allow(_load(settings), rules)),
                        _dump({"permissions": {"allow": rules}})))
    if instructions and (extra := _instructions_change(client)):
        changes.append((*extra, f"{INSTRUCTIONS_MARK}\n{INSTRUCTIONS_LINE}\n"))
    return changes


def create_workspaces(workspace: list[str]) -> list[Path]:
    """Cria as pastas do workspace que ainda não existem; devolve as criadas."""
    created = []
    for w in workspace:
        root = Path(w).expanduser().resolve()
        if not root.exists():
            root.mkdir(parents=True)
            created.append(root)
    return created


def _backup(path: Path, stamp: str) -> Path:
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    backup.write_bytes(path.read_bytes())
    return backup


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)
    if path.suffix == ".json":
        json.loads(path.read_bytes().decode("utf-8"))


def apply(changes: list[tuple[Path, str, str]]) -> list[dict[str, str]]:
    """Grava o que mudou, com backup do que já existia; o que não mudou fica intocado."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    done = []
    for path, text, _ in changes:
        old = path.read_bytes().decode("utf-8") if path.exists() else None
        if old == text:
            done.append({"arquivo": str(path), "acao": "sem mudança"})
            continue
        item = {"arquivo": str(path), "acao": "criado" if old is None else "atualizado"}
        if old is not None:
            item["backup"] = str(_backup(path, stamp))
        _write(path, text)
        done.append(item)
    return done


_BEFORE_WRITE = {
    "claude-code": "Feche o Claude Code antes de gravar: ele reescreve o ~/.claude.json "
                   "enquanto está aberto.",
}
_NOTES = {
    "claude-desktop": "No Claude Desktop não há lista de liberação: na primeira chamada de "
                      "cada tool de leitura, escolha \"sempre permitir\".",
    "kiro": "O mcp.json de um workspace (.kiro/settings/mcp.json) vence o do usuário.",
}
REOPEN = "Feche e abra o cliente e peça o server_info."
SEM_PASTA = ("erro: informe a pasta de estudos com --workspace <pasta> (repita para mais de "
             "uma). Para liberar todas as pastas, use --irrestrito. Nada foi gravado.")


def ask_workspace() -> list[str]:
    """Pergunta as pastas de estudos no terminal; resposta vazia pergunta de novo, sem padrão."""
    print("Em que pasta ficam seus estudos (decks e casos)? O MCP só lê e grava dentro dela.")
    print("Uma pasta por linha; linha vazia termina. Se ainda não tem uma, digite, por "
          f"exemplo, {_home() / 'novomodelo'} (a pasta é criada).")
    pastas: list[str] = []
    while True:
        try:
            linha = input("pasta: ").strip().strip('"')
        except EOFError:
            return pastas
        if linha:
            pastas.append(linha)
        elif pastas:
            return pastas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{MCP_DIST} configurar",
        description="Grava a entrada do MCP no arquivo de configuração do cliente.")
    parser.add_argument("--cliente", choices=CLIENTS, required=True)
    pasta = parser.add_mutually_exclusive_group()
    pasta.add_argument("--workspace", action="append", default=[], metavar="PASTA",
                       help="pasta de estudos permitida (repita para mais de uma)")
    pasta.add_argument("--irrestrito", action="store_true",
                       help="sem pasta de trabalho: o MCP lê e grava em qualquer pasta")
    parser.add_argument("--mostrar", action="store_true",
                        help="só mostra o que seria gravado, sem tocar em nada")
    parser.add_argument("--instrucoes", action="store_true",
                        help="também grava uma linha nas instruções do cliente")
    args = parser.parse_args(argv)
    if not args.workspace and not args.irrestrito:
        if not sys.stdin.isatty():
            print(SEM_PASTA, file=sys.stderr)
            return 2
        args.workspace = ask_workspace()
        if not args.workspace:
            print(SEM_PASTA, file=sys.stderr)
            return 2
    try:
        changes = plan(args.cliente, args.workspace, args.instrucoes)
    except ConfigError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1
    if args.cliente in _BEFORE_WRITE:
        print(_BEFORE_WRITE[args.cliente])
    if not client_found(args.cliente):
        print(f"{CLIENT_NAMES[args.cliente]} não encontrado nesta máquina; a configuração fica "
              "pronta para quando você instalar.")
    if args.mostrar:
        for path, _, fragment in changes:
            print(f"── {path} (só o trecho que muda; o resto do arquivo é mantido)\n{fragment}")
    else:
        try:
            created = create_workspaces(args.workspace)
        except OSError as exc:
            print(f"erro: não foi possível criar a pasta do workspace ({exc}). Nada foi gravado.",
                  file=sys.stderr)
            return 1
        for root in created:
            print(f"pasta criada: {root}")
        for item in apply(changes):
            extra = f" (backup: {item['backup']})" if "backup" in item else ""
            print(f"{item['acao']}: {item['arquivo']}{extra}")
    if args.instrucoes and args.cliente == "claude-desktop":
        print(f"Cole nas preferências do Claude Desktop:\n  {INSTRUCTIONS_LINE}")
    if args.cliente in _NOTES:
        print(_NOTES[args.cliente])
    if not args.mostrar:
        print(REOPEN)
    return 0
