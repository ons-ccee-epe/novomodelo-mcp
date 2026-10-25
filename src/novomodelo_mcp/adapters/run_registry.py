"""Registro das rodadas lançadas pelo MCP: o que entrou em cada `output`.

Para cada `output` guarda o SHA-256 de cada arquivo de entrada do caso e a versão do
executável no lançamento, em `<state>/rodadas/<hash do output>.json`. Fica fora do
`output` (nada é gravado nas pastas da pessoa) e fora dos jobs, que são podados.
Antes de rodar de novo no mesmo `output`, o `run_start` compara o caso atual com o
registrado: igual, mudou (quais arquivos) ou desconhecido (rodada feita por fora).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from ..config import Settings
from .deck_io import INPUT_SUFFIXES, is_run_output
from .state import atomic_write_text, state_dir

_VERSION = re.compile(r"\d+\.\d+\.\d+[^\s]*")


def plain_version(text: str | None) -> str | None:
    """`v0.19.0` ou `novomodelo   v0.19.0` → `0.19.0`."""
    m = _VERSION.search(text or "")
    return m.group(0) if m else None


def input_fingerprint(case_dir: str | Path) -> dict[str, str]:
    """SHA-256 de cada entrada do caso (as mesmas que o `deck_list` lista), por caminho relativo."""
    root = Path(case_dir)
    out: dict[str, str] = {}
    for dirpath, dirs, files in os.walk(root):
        here = Path(dirpath)
        if is_run_output(here) or any((here / fase / "_SUCCESS").exists()
                                      for fase in ("training", "simulation")):
            dirs[:] = []
            continue
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for f in sorted(files):
            p = here / f
            if f.startswith(".") or p.suffix not in INPUT_SUFFIXES:
                continue
            digest = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
            out[p.relative_to(root).as_posix()] = digest.hexdigest()
    return out


def _path(settings: Settings, output: str | Path) -> Path:
    key = hashlib.sha256(str(Path(output).resolve()).encode("utf-8")).hexdigest()[:32]
    return state_dir(settings) / "rodadas" / f"{key}.json"


def record(settings: Settings, *, output: str, case_dir: str, entradas: dict[str, str],
           versao: str | None) -> None:
    path = _path(settings, output)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps({"output": str(Path(output).resolve()), "case_dir": case_dir,
                                        "versao": versao, "entradas": entradas},
                                       indent=2, ensure_ascii=False))


def compare(settings: Settings, *, output: str, entradas: dict[str, str],
            versao: str | None) -> dict[str, Any]:
    """O caso atual contra o registrado para `output`; `caso_igual` None sem registro."""
    try:
        reg = json.loads(_path(settings, output).read_text(encoding="utf-8"))
        antes = dict(reg["entradas"])
    except (OSError, ValueError, KeyError, TypeError):
        return {"caso_igual": None, "versao_atual": versao}
    alterados = sorted(k for k in entradas if k in antes and antes[k] != entradas[k])
    novos = sorted(k for k in entradas if k not in antes)
    removidos = sorted(k for k in antes if k not in entradas)
    anterior = reg.get("versao")
    mesma_versao = anterior is None or versao is None or anterior == versao
    return {"caso_igual": not (alterados or novos or removidos) and mesma_versao,
            "alterados": alterados, "novos": novos, "removidos": removidos,
            "versao_anterior": anterior, "versao_atual": versao}
