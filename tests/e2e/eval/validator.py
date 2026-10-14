"""Validação de respostas MCP contra expectativas do TestCase."""
from __future__ import annotations

from typing import Any

from .models import TestCase


class _Missing:
    """Sentinel para campo ausente."""
    pass


_MISSING = _Missing()


def validate(test_case: TestCase, envelope: dict[str, Any]) -> dict[str, Any]:
    """Valida envelope contra expectativas do TestCase.

    Args:
        test_case: Caso de teste com expectativas
        envelope: Resposta real da tool MCP

    Returns:
        {"valid": True} se passou, ou detalhes da falha:
        {"valid": False, "reason": "...", "details": {...}}
    """
    # 1. Validar status
    actual_status = envelope.get("status")
    if actual_status != test_case.expected_status:
        return {
            "valid": False,
            "reason": f"Status: esperado '{test_case.expected_status}', obtido '{actual_status}'",
            "details": {
                "check": "status",
                "expected": test_case.expected_status,
                "actual": actual_status,
            },
        }

    # 2. Validar campos específicos (se definidos)
    if test_case.expected_fields:
        for path, expected in test_case.expected_fields.items():
            actual = _get_nested(envelope, path)

            if actual is _MISSING:
                return {
                    "valid": False,
                    "reason": f"Campo ausente: '{path}'",
                    "details": {
                        "check": "field_missing",
                        "path": path,
                        "expected": expected,
                    },
                }

            if not _values_match(expected, actual):
                return {
                    "valid": False,
                    "reason": f"Campo '{path}': esperado {expected!r}, obtido {actual!r}",
                    "details": {
                        "check": "field_value",
                        "path": path,
                        "expected": expected,
                        "actual": actual,
                    },
                }

    return {"valid": True}


def _get_nested(obj: Any, path: str) -> Any:
    """Acessa campo por caminho aninhado.

    Suporta:
    - Campos simples: "status"
    - Campos aninhados: "summary.total"
    - Índices de lista: "items[0].name" ou "items.0.name"

    Returns:
        O valor encontrado ou _MISSING se não existir.
    """
    # Normaliza: "items[0]" -> "items.0"
    normalized = path.replace("[", ".").replace("]", "")
    parts = [p for p in normalized.split(".") if p]

    current = obj
    for part in parts:
        if part.isdigit():
            # Acesso por índice
            idx = int(part)
            if not isinstance(current, (list, tuple)):
                return _MISSING
            if idx < 0 or idx >= len(current):
                return _MISSING
            current = current[idx]
        else:
            # Acesso por chave
            if not isinstance(current, dict):
                return _MISSING
            if part not in current:
                return _MISSING
            current = current[part]

    return current


def _values_match(expected: Any, actual: Any) -> bool:
    """Compara valores com suporte a matchers especiais.

    Suporta:
    - Comparação direta de igualdade
    - "__any__": aceita qualquer valor não-None
    - "__nonempty__": aceita string/lista/dict não-vazia
    - "__contains__:texto": verifica se contém substring
    - "__gt__:N": maior que N (numérico)
    - "__gte__:N": maior ou igual a N
    - "__lt__:N": menor que N
    - "__lte__:N": menor ou igual a N
    """
    if expected == "__any__":
        return actual is not None

    if expected == "__nonempty__":
        if actual is None:
            return False
        if isinstance(actual, (str, list, dict)):
            return len(actual) > 0
        return True

    if isinstance(expected, str):
        if expected.startswith("__contains__:"):
            substring = expected[13:]
            return isinstance(actual, str) and substring in actual

        if expected.startswith("__gt__:"):
            threshold = float(expected[7:])
            return isinstance(actual, (int, float)) and actual > threshold

        if expected.startswith("__gte__:"):
            threshold = float(expected[8:])
            return isinstance(actual, (int, float)) and actual >= threshold

        if expected.startswith("__lt__:"):
            threshold = float(expected[7:])
            return isinstance(actual, (int, float)) and actual < threshold

        if expected.startswith("__lte__:"):
            threshold = float(expected[8:])
            return isinstance(actual, (int, float)) and actual <= threshold

    # Comparação direta
    return expected == actual


# Helpers para uso nos casos de teste
def assert_status_ok(envelope: dict[str, Any]) -> bool:
    """Verifica se envelope tem status 'ok'."""
    return envelope.get("status") == "ok"


def assert_status_error(envelope: dict[str, Any]) -> bool:
    """Verifica se envelope tem status 'error'."""
    return envelope.get("status") == "error"


def assert_has_field(envelope: dict[str, Any], path: str) -> bool:
    """Verifica se envelope contém o campo especificado."""
    return _get_nested(envelope, path) is not _MISSING


def assert_field_equals(envelope: dict[str, Any], path: str, expected: Any) -> bool:
    """Verifica se campo tem valor esperado."""
    actual = _get_nested(envelope, path)
    if actual is _MISSING:
        return False
    return _values_match(expected, actual)
