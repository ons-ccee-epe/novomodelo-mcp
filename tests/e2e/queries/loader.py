"""Carrega e valida casos de teste do arquivo YAML.

Este módulo implementa o CasesLoader, responsável por:
- Parsing de arquivos YAML com casos de teste
- Validação do schema usando jsonschema
- Expansão da variável {FIXTURES} para caminhos absolutos
- Filtragem por tags e case_id
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate as json_validate

from tests.e2e.queries.models import (
    ExpectedResult,
    QueryTestCase,
    ValidationSpec,
)

__all__ = ["CasesLoader", "CasesLoaderError"]


class CasesLoaderError(Exception):
    """Erro ao carregar ou validar casos de teste."""

    pass


class CasesLoader:
    """Carrega e valida casos de teste do YAML.

    Attributes:
        cases_path: Caminho para o arquivo cases.yaml
        fixtures_dir: Diretório de fixtures (resolvido para caminho absoluto)

    Example:
        >>> loader = CasesLoader(Path("cases.yaml"), Path("fixtures"))
        >>> cases = loader.load(tags=["bridge"])
        >>> for case in cases:
        ...     print(case.id)
    """

    # JSON Schema para validação do YAML
    SCHEMA: dict[str, Any] = {
        "type": "array",
        "items": {
            "type": "object",
            "required": ["id", "query", "expected"],
            "additionalProperties": False,
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "query": {"type": "string", "minLength": 1},
                "expected": {
                    "type": "object",
                    "required": ["uses_mcp"],
                    "additionalProperties": False,
                    "properties": {
                        "uses_mcp": {"type": "boolean"},
                        "tool": {"type": "string", "minLength": 1},
                        "tools": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                        },
                        "status": {"type": "string", "enum": ["ok", "error"]},
                        "content": {"type": "object"},
                        "did_not_use": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                        "validation": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "cites_section_pattern": {"type": "string"},
                                "response_contains": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                        "error_contains": {"type": "string"},
                    },
                    "oneOf": [
                        {"required": ["tool"]},
                        {"required": ["tools"]},
                        {
                            "not": {
                                "anyOf": [
                                    {"required": ["tool"]},
                                    {"required": ["tools"]},
                                ]
                            }
                        },
                    ],
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    }

    def __init__(self, cases_path: Path, fixtures_dir: Path) -> None:
        """Inicializa o loader.

        Args:
            cases_path: Caminho para o arquivo cases.yaml
            fixtures_dir: Diretório de fixtures (será resolvido para absoluto)
        """
        self.cases_path = cases_path
        self.fixtures_dir = fixtures_dir.resolve()

    def load(
        self,
        tags: list[str] | None = None,
        case_id: str | None = None,
    ) -> list[QueryTestCase]:
        """Carrega casos de teste, opcionalmente filtrados.

        Args:
            tags: Filtrar por tags (OR logic - caso deve ter pelo menos uma)
            case_id: Carregar apenas um caso específico por ID

        Returns:
            Lista de QueryTestCase validados com {FIXTURES} expandido

        Raises:
            CasesLoaderError: Se arquivo não existe, YAML inválido,
                ou schema não passa validação
        """
        raw_cases = self._load_yaml()
        self._validate_schema(raw_cases)
        self._validate_unique_ids(raw_cases)
        self._validate_tool_requirements(raw_cases)

        # Converter para dataclasses
        cases = [self._to_test_case(raw) for raw in raw_cases]

        # Filtrar por case_id
        if case_id is not None:
            cases = [c for c in cases if c.id == case_id]
            if not cases:
                raise CasesLoaderError(f"Caso de teste não encontrado: {case_id}")

        # Filtrar por tags (OR logic)
        if tags is not None and tags:
            tags_set = set(tags)
            cases = [c for c in cases if tags_set & set(c.tags)]

        return cases

    def _load_yaml(self) -> list[dict[str, Any]]:
        """Carrega o arquivo YAML.

        Returns:
            Lista de dicts representando os casos de teste

        Raises:
            CasesLoaderError: Se arquivo não existe ou YAML inválido
        """
        if not self.cases_path.exists():
            raise CasesLoaderError(f"Arquivo não encontrado: {self.cases_path}")

        try:
            with self.cases_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise CasesLoaderError(f"Erro ao parsear YAML: {e}") from e

        if data is None:
            return []

        if not isinstance(data, list):
            raise CasesLoaderError(
                f"YAML deve ser uma lista de casos de teste, obtido: {type(data).__name__}"
            )

        return data

    def _validate_schema(self, raw_cases: list[dict[str, Any]]) -> None:
        """Valida o schema JSON dos casos de teste.

        Args:
            raw_cases: Lista de dicts a validar

        Raises:
            CasesLoaderError: Se schema não passa validação
        """
        try:
            json_validate(instance=raw_cases, schema=self.SCHEMA)
        except JsonSchemaValidationError as e:
            # Formatar mensagem amigável
            path = " -> ".join(str(p) for p in e.absolute_path) if e.absolute_path else "root"
            raise CasesLoaderError(f"Schema inválido em '{path}': {e.message}") from e

    def _validate_unique_ids(self, raw_cases: list[dict[str, Any]]) -> None:
        """Valida que todos os IDs são únicos.

        Args:
            raw_cases: Lista de dicts a validar

        Raises:
            CasesLoaderError: Se houver IDs duplicados
        """
        ids = [case["id"] for case in raw_cases]
        seen: set[str] = set()
        duplicates: list[str] = []
        for id_ in ids:
            if id_ in seen:
                duplicates.append(id_)
            seen.add(id_)

        if duplicates:
            raise CasesLoaderError(f"IDs duplicados encontrados: {duplicates}")

    def _validate_tool_requirements(self, raw_cases: list[dict[str, Any]]) -> None:
        """Valida que quando uses_mcp=True, tool ou tools está definido.

        Args:
            raw_cases: Lista de dicts a validar

        Raises:
            CasesLoaderError: Se uses_mcp=True sem tool/tools
        """
        for case in raw_cases:
            expected = case["expected"]
            uses_mcp = expected.get("uses_mcp", False)

            if uses_mcp:
                has_tool = "tool" in expected
                has_tools = "tools" in expected

                if not has_tool and not has_tools:
                    raise CasesLoaderError(
                        f"Caso '{case['id']}': quando uses_mcp=True, "
                        "'tool' ou 'tools' deve ser definido"
                    )

    def _expand_fixtures(self, query: str) -> str:
        """Expande {FIXTURES} para caminho absoluto.

        Args:
            query: Query com possível variável {FIXTURES}

        Returns:
            Query com {FIXTURES} substituído pelo caminho absoluto do fixtures_dir
        """
        return query.replace("{FIXTURES}", str(self.fixtures_dir))

    def _to_test_case(self, raw: dict[str, Any]) -> QueryTestCase:
        """Converte dict YAML para QueryTestCase dataclass.

        Args:
            raw: Dict do YAML representando um caso de teste

        Returns:
            QueryTestCase com campos validados e query expandida
        """
        expected_raw = raw["expected"]

        # Construir ValidationSpec se presente
        validation_spec: ValidationSpec | None = None
        if "validation" in expected_raw:
            val_raw = expected_raw["validation"]
            validation_spec = ValidationSpec(
                cites_section_pattern=val_raw.get("cites_section_pattern"),
                response_contains=val_raw.get("response_contains"),
            )

        # Construir ExpectedResult
        expected = ExpectedResult(
            uses_mcp=expected_raw["uses_mcp"],
            tool=expected_raw.get("tool"),
            tools=expected_raw.get("tools"),
            status=expected_raw.get("status"),
            content=expected_raw.get("content"),
            did_not_use=expected_raw.get("did_not_use"),
            validation=validation_spec,
            error_contains=expected_raw.get("error_contains"),
        )

        # Construir QueryTestCase com query expandida
        return QueryTestCase(
            id=raw["id"],
            query=self._expand_fixtures(raw["query"]),
            expected=expected,
            tags=tuple(raw.get("tags", [])),
        )
