"""Data models para o framework de avaliação de tools MCP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TestCase:
    """Define um cenário de teste para uma tool MCP.

    Attributes:
        tool_name: Nome da tool MCP (ex: "bridge_check_newave")
        case_id: Identificador único do caso (ex: "valid_newave_ago26")
        description: Descrição legível do teste
        parameters: Parâmetros a passar para a tool
        expected_status: Status esperado no envelope ("ok" ou "error")
        expected_fields: Campos específicos a validar no envelope (opcional)
        tags: Tags para categorização/filtragem (ex: ("functional", "newave"))
        timeout_seconds: Timeout máximo para execução
    """

    tool_name: str
    case_id: str
    description: str
    parameters: dict[str, Any]
    expected_status: str
    expected_fields: dict[str, Any] | None = None
    tags: tuple[str, ...] = ()
    timeout_seconds: float = 60.0

    def full_id(self) -> str:
        """Retorna identificador completo: tool_name/case_id."""
        return f"{self.tool_name}/{self.case_id}"


@dataclass
class ExecutionResult:
    """Resultado da execução de um caso de teste.

    Attributes:
        test_case: O caso de teste executado
        envelope: Resposta real retornada pela tool MCP
        execution_time_ms: Tempo de execução em milissegundos
        status: Status do teste ("passed", "failed", "error", "skipped")
        timestamp: Momento da execução
        failure_reason: Razão da falha (se status != "passed")
        validation_details: Detalhes da validação (campo, esperado, obtido)
    """

    test_case: TestCase
    envelope: dict[str, Any]
    execution_time_ms: float
    status: str  # "passed", "failed", "error", "skipped"
    timestamp: datetime = field(default_factory=datetime.now)
    failure_reason: str | None = None
    validation_details: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        """True se o teste passou."""
        return self.status == "passed"


@dataclass(frozen=True)
class MetricRecord:
    """Registro de métrica para persistência em JSONL.

    Attributes:
        tool_name: Nome da tool
        case_id: ID do caso de teste
        status: Status do teste
        execution_time_ms: Tempo de execução
        timestamp: ISO 8601 timestamp
        environment: "local" ou URL do servidor
        error_message: Mensagem de erro (se houver)
        cobre_mcp_version: Versão do pacote cobre-mcp
        git_commit_sha: SHA do commit atual
    """

    tool_name: str
    case_id: str
    status: str
    execution_time_ms: float
    timestamp: str
    environment: str
    error_message: str | None = None
    cobre_mcp_version: str = "unknown"
    git_commit_sha: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário (para serialização JSON)."""
        return {
            "tool_name": self.tool_name,
            "case_id": self.case_id,
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
            "environment": self.environment,
            "error_message": self.error_message,
            "cobre_mcp_version": self.cobre_mcp_version,
            "git_commit_sha": self.git_commit_sha,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricRecord:
        """Cria instância a partir de dicionário."""
        return cls(
            tool_name=data["tool_name"],
            case_id=data["case_id"],
            status=data["status"],
            execution_time_ms=data["execution_time_ms"],
            timestamp=data["timestamp"],
            environment=data["environment"],
            error_message=data.get("error_message"),
            cobre_mcp_version=data.get("cobre_mcp_version", "unknown"),
            git_commit_sha=data.get("git_commit_sha", "unknown"),
        )

    @classmethod
    def from_execution_result(
        cls, result: ExecutionResult, environment: str,
        version: str = "unknown", git_sha: str = "unknown"
    ) -> MetricRecord:
        """Cria MetricRecord a partir de ExecutionResult."""
        return cls(
            tool_name=result.test_case.tool_name,
            case_id=result.test_case.case_id,
            status=result.status,
            execution_time_ms=result.execution_time_ms,
            timestamp=result.timestamp.isoformat(),
            environment=environment,
            error_message=result.failure_reason,
            cobre_mcp_version=version,
            git_commit_sha=git_sha,
        )
