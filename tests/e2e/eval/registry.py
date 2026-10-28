"""Registro de casos de teste com auto-descoberta."""

from __future__ import annotations

import importlib
import sys
from collections import defaultdict
from pathlib import Path

from .models import TestCase


class TestRegistry:
    """Catálogo de casos de teste organizados por tool.

    Permite registro manual e auto-descoberta de arquivos test_*.py.
    """

    def __init__(self) -> None:
        self._cases: dict[str, dict[str, TestCase]] = defaultdict(dict)

    def register(self, case: TestCase) -> None:
        """Registra um caso de teste.

        Raises:
            ValueError: Se campos obrigatórios faltam ou case_id duplicado.
        """
        self._validate(case)

        if case.case_id in self._cases[case.tool_name]:
            raise ValueError(f"case_id duplicado: {case.tool_name}/{case.case_id}")

        self._cases[case.tool_name][case.case_id] = case

    def _validate(self, case: TestCase) -> None:
        """Valida campos obrigatórios de um TestCase."""
        required = ["tool_name", "case_id", "description", "parameters", "expected_status"]
        for field in required:
            value = getattr(case, field, None)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Campo obrigatório vazio: {field}")

    def get_by_tool(self, tool_name: str) -> list[TestCase]:
        """Retorna todos os casos de uma tool específica."""
        return list(self._cases.get(tool_name, {}).values())

    def get_by_tag(self, tag: str) -> list[TestCase]:
        """Retorna casos que contêm a tag especificada."""
        result = []
        for cases in self._cases.values():
            for case in cases.values():
                if tag in case.tags:
                    result.append(case)
        return result

    def get_all(self) -> list[TestCase]:
        """Retorna todos os casos registrados."""
        result = []
        for cases in self._cases.values():
            result.extend(cases.values())
        return result

    def tools(self) -> list[str]:
        """Retorna lista de tools com casos registrados."""
        return list(self._cases.keys())

    def count(self) -> int:
        """Retorna total de casos registrados."""
        return sum(len(cases) for cases in self._cases.values())

    def __len__(self) -> int:
        return self.count()


def discover_cases(registry: TestRegistry, cases_dir: Path) -> int:
    """Detecta e registra casos de arquivos test_*.py.

    Cada arquivo deve ter uma função `register(registry)` ou uma
    variável `CASES` (lista de TestCase).

    Args:
        registry: Registry para registrar os casos
        cases_dir: Diretório com arquivos test_*.py

    Returns:
        Número de casos descobertos e registrados.
    """
    if not cases_dir.is_dir():
        return 0

    # Adiciona cases_dir ao path para importação
    cases_dir_str = str(cases_dir.resolve())
    if cases_dir_str not in sys.path:
        sys.path.insert(0, cases_dir_str)

    count_before = registry.count()

    for path in sorted(cases_dir.glob("test_*.py")):
        module_name = path.stem
        try:
            module = importlib.import_module(module_name)

            # Tenta função register(registry)
            if hasattr(module, "register") and callable(module.register):
                module.register(registry)

            # Tenta variável CASES
            elif hasattr(module, "CASES"):
                cases = module.CASES
                if isinstance(cases, list):
                    for case in cases:
                        if isinstance(case, TestCase):
                            registry.register(case)

        except Exception as e:
            print(f"Aviso: falha ao carregar {path.name}: {e}")

    return registry.count() - count_before
