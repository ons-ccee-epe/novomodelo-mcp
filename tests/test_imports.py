"""Importa todos os submódulos do pacote — pega import quebrado em qualquer arquivo.

É o gate que teria pego o bug recorrente `from .config` -> `..config` na hora,
sem depender de rodar o smoke certo. Requer as deps instaladas (mcp etc.), o que
o CI garante via `uv sync`.
"""
import importlib
import pkgutil

import cobre_mcp


def test_all_submodules_import():
    for mod in pkgutil.walk_packages(cobre_mcp.__path__, cobre_mcp.__name__ + "."):
        importlib.import_module(mod.name)
