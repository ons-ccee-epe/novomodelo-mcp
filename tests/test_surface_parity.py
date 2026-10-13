"""Paridade entre as tools e o que o novomodelo, o bridge e a biblioteca oferecem.

O manifesto `tests/surface.toml` classifica cada subcomando, opção e função pública.
Com os programas reais instalados, o `--help` deles é comparado ao manifesto; sem
eles, esses testes pulam e só os testes do próprio detector (com ajuda fixa) rodam.
"""
import importlib
import os
import re
import subprocess
import tomllib
import types
from pathlib import Path

import pytest

import novomodelo_mcp
from novomodelo_mcp.adapters.discovery import find_bridge, find_novomodelo
from novomodelo_mcp.config import load_settings
from novomodelo_mcp.server import build_server

MANIFEST = tomllib.loads(Path(__file__).with_name("surface.toml").read_text(encoding="utf-8"))
SRC = Path(novomodelo_mcp.__file__).resolve().parent
PROGRAMS = ("novomodelo", "bridge")
ADAPTER = {"novomodelo": SRC / "adapters" / "novomodelo.py", "bridge": SRC / "adapters" / "bridge.py"}
_META_KEYS = {"raiz", "ignorados"}

# clap indenta a opção em até 6 espaços (a descrição vem mais funda); o Typer abre a
# linha com "│ ", ou "| " quando o console não é UTF-8. Formas curtas (`-o`) são
# ignoradas: só a longa conta.
_BORDERS = "│|"
_OPTION_LINE = re.compile(r"^(?:[│|] |\s{2,6})(?:-[A-Za-z],\s*)?(--[a-z][a-z0-9-]*)")
_COMMANDS_HEADER = re.compile(r"^(?:Commands:|[╭+][─-] Commands)")


def parse_options(help_text: str) -> set[str]:
    return {m.group(1) for line in help_text.splitlines() if (m := _OPTION_LINE.match(line))}


def _row(line: str) -> str:
    row = line.rstrip()
    row = row[1:] if row[:1] in _BORDERS else row
    return row[:-1].rstrip() if row[-1:] in _BORDERS else row


def parse_commands(help_text: str) -> set[str]:
    # Uma linha mais indentada que a primeira do bloco continua a descrição anterior:
    # o runner do CI quebra a ajuda em 80 colunas e ignora `COLUMNS`.
    names, inside, indent = set(), False, None
    for line in help_text.splitlines():
        if _COMMANDS_HEADER.match(line.strip()):
            inside = True
            continue
        if inside:
            row = _row(line)
            if not row.strip() or line.strip().startswith(("╰", "+", "Options:")):
                break
            depth = len(row) - len(row.lstrip())
            indent = depth if indent is None else indent
            if depth == indent:
                names.add(row.split()[0])
    return names


def option_gaps(found: set[str], entry: dict, label: str) -> list[str]:
    known = set(entry.get("expostas", [])) | set(entry.get("ignoradas", {}))
    return ([f"opção nova em `{label}`: `{o}` — exponha na tool ou marque como "
             f"ignorada em `tests/surface.toml`" for o in sorted(found - known)]
            + [f"opção sumiu de `{label}`: `{o}` — tire de `tests/surface.toml`"
               for o in sorted(known - found)])


def _binary(program: str) -> str | None:
    settings = load_settings()
    return find_novomodelo(settings) if program == "novomodelo" else find_bridge(settings)


def _help(binary: str, words: list[str]) -> str:
    env = {**os.environ, "NO_COLOR": "1", "COLUMNS": "200", "TERM": "dumb",
           "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([binary, *words, "--help"], capture_output=True, text=True,
                          timeout=60, env=env)
    return proc.stdout + proc.stderr


def _subcommands(program: str) -> list[str]:
    return [k for k in MANIFEST[program] if k not in _META_KEYS]


def _require(program: str) -> str:
    binary = _binary(program)
    if binary is None:
        pytest.skip(f"{'novomodelo' if program == 'novomodelo' else 'novomodelo-bridge'} "
                    "não instalado")
    return binary


# ── com os programas reais ────────────────────────────────────────────────────

@pytest.mark.parametrize("program", PROGRAMS)
def test_todo_subcomando_esta_no_manifesto(program):
    binary = _require(program)
    leaves, groups = set(), []
    for name in parse_commands(_help(binary, [])):
        children = parse_commands(_help(binary, [name]))
        if children:
            groups.append(name)
            leaves |= {f"{name} {c}" for c in children if c != "help"}
        else:
            leaves.add(name)
    known = set(_subcommands(program)) | set(MANIFEST[program]["ignorados"])
    assert sorted(leaves - known) == [], f"subcomando novo em {program}: sem entrada no manifesto"
    assert sorted(known - leaves) == [], f"subcomando sumiu de {program}"
    root = MANIFEST[program]["raiz"]
    globais = {"--help", *root["expostas"], *root["ignoradas"]}
    for group in groups:
        extra = parse_options(_help(binary, [group])) - globais
        assert not extra, f"opção de grupo em `{program} {group}`: {sorted(extra)}"


@pytest.mark.parametrize("program,sub", [(p, s) for p in PROGRAMS
                                         for s in ["raiz", *_subcommands(p)]])
def test_toda_opcao_esta_no_manifesto(program, sub):
    binary = _require(program)
    words = [] if sub == "raiz" else sub.split()
    found = parse_options(_help(binary, words))
    gaps = option_gaps(found, MANIFEST[program][sub], f"{program} {sub}")
    assert not gaps, "\n".join(gaps)


def _library_names(novomodelo) -> set[str]:
    names = set()
    for top in novomodelo.__all__:
        obj = getattr(novomodelo, top)
        if not isinstance(obj, types.ModuleType):
            names.add(top)
            continue
        names |= {f"{top}.{n}" for n in dir(obj) if not n.startswith("_")
                  and not isinstance(getattr(obj, n), types.ModuleType)}
    return names


def library_gaps(novomodelo) -> list[str]:
    found, known = _library_names(novomodelo), set(MANIFEST["biblioteca"])
    return ([f"função pública nova na biblioteca: `{n}` — dê uma tool ou marque "
             f"nao_exposto/pendente em `tests/surface.toml`" for n in sorted(found - known)]
            + [f"sumiu da biblioteca: `{n}`" for n in sorted(known - found)])


def _library():
    try:
        return importlib.import_module("novomodelo")
    except ImportError:
        pytest.skip("novomodelo-python não instalado")


def test_toda_funcao_publica_da_biblioteca_esta_no_manifesto():
    gaps = library_gaps(_library())
    assert not gaps, "\n".join(gaps)


def test_funcao_nova_simulada_na_biblioteca_e_acusada(monkeypatch):
    novomodelo = _library()
    monkeypatch.setattr(novomodelo.io, "funcao_nova", lambda: None, raising=False)
    assert any("io.funcao_nova" in g for g in library_gaps(novomodelo))


def test_itens_pendentes():
    pendentes = sorted(k for k, v in MANIFEST["biblioteca"].items() if "pendente" in v)
    if pendentes:
        pytest.xfail(f"pendentes (precisam chegar a zero antes do release): {pendentes}")


# ── sem os programas: manifesto × código das tools ────────────────────────────

def _tool_modules() -> dict[str, Path]:
    return {t.name: Path(importlib.import_module(t.fn.__module__).__file__)
            for t in build_server()._tool_manager.list_tools()}


def test_toda_tool_do_manifesto_existe():
    tools = set(_tool_modules())
    named = {e["tool"] for p in PROGRAMS for s in _subcommands(p)
             for e in [MANIFEST[p][s]]} | {v["tool"] for v in MANIFEST["biblioteca"].values()
                                           if "tool" in v}
    assert sorted(named - tools) == []


@pytest.mark.parametrize("program,sub", [(p, s) for p in PROGRAMS
                                         for s in ["raiz", *_subcommands(p)]])
def test_opcao_exposta_aparece_no_codigo(program, sub):
    entry = MANIFEST[program][sub]
    if sub == "raiz":
        source = "".join(f.read_text(encoding="utf-8") for f in (SRC / "adapters").glob("*.py"))
    else:
        source = (_tool_modules()[entry["tool"]].read_text(encoding="utf-8")
                  + ADAPTER[program].read_text(encoding="utf-8"))
    missing = [o for o in entry["expostas"] if f'"{o}"' not in source]
    assert not missing, f"`{program} {sub}`: exposta no manifesto mas ausente do código: {missing}"


def test_manifesto_nao_classifica_opcao_duas_vezes():
    for p in PROGRAMS:
        for s in ["raiz", *_subcommands(p)]:
            entry = MANIFEST[p][s]
            assert not set(entry["expostas"]) & set(entry["ignoradas"]), f"{p} {s}"


# ── o detector, com ajuda fixa (roda no CI) ───────────────────────────────────

CLAP_HELP = """Usage: novomodelo run [OPTIONS] <CASE_DIR>

Commands:
  export  Export JSON Schema files
  help    Print this message

Options:
      --color <COLOR>
          Control ANSI color output on stderr.
          --json aparece aqui só como texto da descrição
  -o, --output <DIR>
  -h, --help
"""
TYPER_HELP = """ Usage: novomodelo-bridge convert decomp [OPTIONS] {src} {dst}
╭─ Commands ──────────────────╮
│ newave  Convert a NEWAVE    │
│ decomp  Convert a DECOMP    │
╰─────────────────────────────╯
╭─ Options ───────────────────╮
│ --force                Overwrite.                │
│ --no-fcf               Skip the FCF. Always      │
│                        skipped under --dry-run.  │
│ --verbose   -v  <int>  Verbosity.                │
╰─────────────────────────────╯
"""


TYPER_HELP_80_COLUNAS = """ Usage: novomodelo-bridge [OPTIONS] COMMAND [ARGS]...
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --show-completion             Show completion for the current shell, to copy │
│                               it or customize the installation.              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ dashboard  Generate an interactive HTML dashboard from Novomodelo simulation │
│            results.                                                          │
│ convert    Convert data from a source format to Novomodelo JSON.             │
╰──────────────────────────────────────────────────────────────────────────────╯
"""
TYPER_HELP_ASCII = """ Usage: novomodelo-bridge [OPTIONS] COMMAND [ARGS]...
+- Options --------------------------------------------------------------------+
| --version                     Show the version and exit.                     |
| --show-completion             Show completion for the current shell, to copy |
|                               it or customize the installation.              |
+------------------------------------------------------------------------------+
+- Commands -------------------------------------------------------------------+
| dashboard  Generate an interactive HTML dashboard from Novomodelo simulation |
|            results.                                                          |
| convert    Convert data from a source format to Novomodelo JSON.             |
+------------------------------------------------------------------------------+
"""
CLAP_HELP_80_COLUNAS = """Usage: novomodelo [OPTIONS] <COMMAND>

Commands:
  validate  Validate a case directory and print a structured diagnostic
            report
  version   Print version, solver backend, and build information

Options:
  -h, --help
"""


def test_parse_das_opcoes_clap_e_typer():
    assert parse_options(CLAP_HELP) == {"--color", "--output", "--help"}
    assert parse_options(TYPER_HELP) == {"--force", "--no-fcf", "--verbose"}


def test_parse_dos_subcomandos_clap_e_typer():
    assert parse_commands(CLAP_HELP) == {"export", "help"}
    assert parse_commands(TYPER_HELP) == {"newave", "decomp"}


def test_parse_ignora_continuacao_da_descricao_quebrada_em_80_colunas():
    assert parse_commands(TYPER_HELP_80_COLUNAS) == {"dashboard", "convert"}
    assert parse_commands(CLAP_HELP_80_COLUNAS) == {"validate", "version"}
    assert parse_options(TYPER_HELP_80_COLUNAS) == {"--show-completion"}


def test_parse_aceita_borda_ascii():
    assert parse_commands(TYPER_HELP_ASCII) == {"dashboard", "convert"}
    assert parse_options(TYPER_HELP_ASCII) == {"--version", "--show-completion"}


def test_detector_acusa_opcao_nova_e_opcao_sumida():
    entry = {"expostas": ["--force"], "ignoradas": {"--help": "ajuda", "--velha": "x"}}
    gaps = option_gaps({"--force", "--help", "--nova"}, entry, "bridge x")
    assert any("opção nova" in g and "--nova" in g for g in gaps)
    assert any("sumiu" in g and "--velha" in g for g in gaps)
