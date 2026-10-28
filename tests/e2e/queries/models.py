"""Data models para o framework de testes E2E via query.

Este módulo define todas as estruturas de dados usadas pelo framework:
- Definições de casos de teste (QueryTestCase, ExpectedResult, ValidationSpec)
- Resultados de execução (ToolCall, QueryResult)
- Resultados de validação (ValidationCheck, ValidationResult)
- Resultados de bateria (TestResult, BatchResult, BatchMetrics, TagMetrics, GroupMetrics)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    # Definição de casos de teste
    "QueryTestCase",
    "ExpectedResult",
    "ValidationSpec",
    # Execução
    "ToolCall",
    "QueryResult",
    # Validação
    "ValidationCheck",
    "ValidationResult",
    # Resultados de bateria
    "TestResult",
    "BatchResult",
    "BatchMetrics",
    "TagMetrics",
    "GroupMetrics",
]


# =============================================================================
# Definições de Casos de Teste
# =============================================================================


@dataclass(frozen=True)
class ValidationSpec:
    """Especificação de validações adicionais para documentação.

    Attributes:
        cites_section_pattern: Regex para validar citação de docs (formato página#seção)
        response_contains: Lista de keywords que devem estar na resposta do agente
    """

    cites_section_pattern: str | None = None
    response_contains: list[str] | None = None


@dataclass(frozen=True)
class ExpectedResult:
    """Expectativas de resultado para validação de um caso de teste.

    Attributes:
        uses_mcp: Se True, o agente deve ter chamado pelo menos uma MCP_Tool
        tool: Tool específica esperada (mutuamente exclusivo com tools)
        tools: Lista de tools aceitáveis - qualquer uma é válida (mutuamente exclusivo com tool)
        status: Status esperado do envelope ("ok" ou "error")
        content: Validações de campos do envelope usando path -> matcher
        did_not_use: Lista de tools que NÃO devem ter sido usadas
        validation: Validações adicionais para citações e keywords
        error_contains: Substring esperada na mensagem de erro

    Note:
        Os campos `tool` e `tools` são mutuamente exclusivos. O schema YAML
        requer que exatamente um deles seja definido quando uses_mcp=True.
    """

    uses_mcp: bool
    tool: str | None = None
    tools: list[str] | None = None
    status: str | None = None
    content: dict[str, Any] | None = None
    did_not_use: list[str] | None = None
    validation: ValidationSpec | None = None
    error_contains: str | None = None


@dataclass(frozen=True)
class QueryTestCase:
    """Define um caso de teste via query em linguagem natural.

    Um QueryTestCase representa um único teste E2E que envia uma pergunta
    ao Kiro CLI e valida se a tool MCP correta foi chamada e se a resposta
    está correta.

    Attributes:
        id: Identificador único do caso (ex: "check-newave-valid")
        query: Query em linguagem natural, com suporte a variável {FIXTURES}
        expected: Expectativas de validação para o resultado
        tags: Tags para categorização e filtragem (ex: ("bridge", "newave"))

    Example:
        ```yaml
        - id: check-newave-valid
          query: Valide o caso NEWAVE em {FIXTURES}/newave/ago26
          expected:
            uses_mcp: true
            tool: bridge_check_newave
            status: ok
          tags: [bridge, newave, validation]
        ```
    """

    id: str
    query: str
    expected: ExpectedResult
    tags: tuple[str, ...] = ()
    # Fontes (decks/casos) que precisam existir para o teste fazer sentido;
    # caminhos absolutos, com {FIXTURES} já expandido.
    requires: tuple[str, ...] = ()
    # Timeout efetivo do caso (s), já resolvido: caso > grupo > default do YAML.
    timeout_s: float | None = None


# =============================================================================
# Resultados de Execução
# =============================================================================


@dataclass
class ToolCall:
    """Uma chamada de tool extraída do log do Kiro CLI.

    Attributes:
        name: Nome da tool chamada (ex: "deck_list", "read_file")
        args: Argumentos passados para a tool como dicionário
        tool_id: ID único da tool call se disponível (ex: "toolu_bdrk_...")
    """

    name: str
    args: dict[str, Any]
    tool_id: str | None = None


@dataclass
class QueryResult:
    """Resultado da execução de uma query via Kiro CLI.

    Attributes:
        test_case: O caso de teste que foi executado
        tool_calls: Lista de todas as tool calls detectadas no log
        agent_response: Resposta final do agente ao usuário
        latency_ms: Tempo total de execução em milissegundos
        status: Status da execução ("completed", "timeout", "error")
        stdout: Saída padrão capturada do Kiro CLI
        stderr: Saída de erro capturada do Kiro CLI
        envelope: Envelope MCP da tool principal, se disponível
    """

    test_case: QueryTestCase
    tool_calls: list[ToolCall]
    agent_response: str
    latency_ms: float
    status: str  # "completed", "timeout", "cancelled", "error"
    stdout: str
    stderr: str
    envelope: dict[str, Any] | None = None
    timeout_s: float | None = None  # limite aplicado nesta execução


# =============================================================================
# Resultados de Validação
# =============================================================================


@dataclass
class ValidationCheck:
    """Uma verificação individual de validação.

    Cada ValidationCheck representa uma única asserção verificada durante
    a validação de um resultado de query.

    Attributes:
        name: Nome da verificação (ex: "uses_mcp", "correct_tool", "status")
        passed: True se a verificação passou
        expected: Valor esperado conforme definido no caso de teste
        actual: Valor obtido da execução
        message: Mensagem descritiva do resultado da verificação
    """

    name: str
    passed: bool
    expected: Any
    actual: Any
    message: str


@dataclass
class ValidationResult:
    """Resultado completo da validação de uma query.

    Attributes:
        valid: True se todas as verificações passaram
        status: Status final da validação ("pass", "fail", "timeout", "skip")
        checks: Lista de todas as verificações realizadas
        failure_reason: Razão da falha se valid=False
        details: Detalhes adicionais para diagnóstico
    """

    valid: bool
    status: (
        str  # "pass", "partial", "fail", "timeout", "skip" (partial = MCP ok but validation failed)
    )
    checks: list[ValidationCheck]
    failure_reason: str | None = None
    details: dict[str, Any] | None = None


# =============================================================================
# Resultados de Bateria
# =============================================================================


@dataclass
class TestResult:
    """Resultado detalhado de um teste individual dentro de uma bateria.

    Este modelo é usado para persistência em JSON e contém todos os dados
    necessários para diagnóstico e análise posterior.

    Attributes:
        test_id: ID do caso de teste executado
        query: Query executada (com {FIXTURES} já expandido)
        expected_tool: Tool esperada se definida como única
        expected_tools: Lista de tools esperadas se definida como lista
        actual_tool: Tool principal que foi chamada (primeira MCP tool, ou primeira tool)
        all_tool_calls: Lista de todas as tool calls como dicts serializáveis
        status: Status do teste ("pass", "fail", "timeout", "skip")
        latency_ms: Tempo total de execução em milissegundos
        tool_latency_ms: Tempo específico da tool se disponível
        mcp_used: True se pelo menos uma MCP_Tool foi chamada
        correct_tool: True se a tool correta foi chamada
        correct_result: True se o resultado passou em todas as validações
        agent_response: Resposta completa do agente para diagnóstico
        error_message: Mensagem de erro se status não é "pass"
        tags: Lista de tags do caso de teste
        validation_checks: Lista de verificações realizadas como dicts
    """

    test_id: str
    query: str
    expected_tool: str | None
    expected_tools: list[str] | None
    actual_tool: str | None
    all_tool_calls: list[dict[str, Any]]
    status: (
        str  # "pass", "partial", "fail", "timeout", "skip" (partial = MCP ok but validation failed)
    )
    latency_ms: float
    tool_latency_ms: float | None
    mcp_used: bool
    correct_tool: bool
    correct_result: bool
    agent_response: str
    error_message: str | None
    tags: list[str]
    validation_checks: list[dict[str, Any]]


@dataclass
class BatchMetrics:
    """Métricas agregadas de uma bateria de testes.

    Attributes:
        pct_mcp_used: Percentual de testes que usaram MCP (0-100)
        pct_correct_tool: Percentual de testes com tool correta (0-100)
        pct_correct_result: Percentual de testes com resultado correto (0-100)
        avg_latency_ms: Latência média em milissegundos
        p95_latency_ms: Latência percentil 95 em milissegundos
        passed_full: Testes que passaram em todas as validações
        passed_mcp_only: Testes que usaram MCP corretamente mas falharam validação de resultado
        failed_no_mcp: Testes que não usaram MCP quando deveriam
        failed_wrong_tool: Testes que usaram tool MCP errada
        failed_other: Outras falhas (timeout, erro, etc)
    """

    pct_mcp_used: float
    pct_correct_tool: float
    pct_correct_result: float
    avg_latency_ms: float
    p95_latency_ms: float
    passed_full: int = 0
    passed_mcp_only: int = 0
    failed_no_mcp: int = 0
    failed_wrong_tool: int = 0
    failed_other: int = 0


@dataclass
class TagMetrics:
    """Métricas agregadas por tag.

    Attributes:
        total: Total de testes com esta tag
        passed: Quantidade que passou
        failed: Quantidade que falhou
        mcp_used: Quantidade que usou MCP
        correct_tool: Quantidade que usou a tool correta
    """

    total: int
    passed: int
    failed: int
    mcp_used: int
    correct_tool: int


@dataclass
class GroupMetrics:
    """Métricas agregadas por grupo de tools.

    Os grupos são: bridge, deck, docs, results, schema, run, case, meta, other.

    Attributes:
        total: Total de testes neste grupo
        pct_pass: Percentual de testes que passaram (0-100)
        pct_mcp_used: Percentual de testes que usaram MCP (0-100)
        pct_correct_tool: Percentual de testes com tool correta (0-100)
        avg_latency_ms: Latência média em milissegundos
    """

    total: int
    pct_pass: float
    pct_mcp_used: float
    pct_correct_tool: float
    avg_latency_ms: float


@dataclass
class BatchResult:
    """Resultado completo de uma bateria de testes.

    Este modelo representa o resultado persistido de uma execução completa
    de testes, incluindo todos os resultados individuais e métricas agregadas.

    Attributes:
        batch_id: ID único no formato {timestamp}_{git_sha} (ex: "20241215_143052_abc1234")
        timestamp: ISO 8601 timestamp da execução
        mcp_version: Versão do pacote novomodelo-mcp
        git_commit_sha: SHA completo do commit Git
        environment: Identificador do ambiente ("local" ou outro)
        total_tests: Total de testes executados
        passed: Quantidade de testes que passaram
        failed: Quantidade de testes que falharam
        skipped: Quantidade de testes pulados
        timeout: Quantidade de testes com timeout
        test_results: Lista de TestResult para cada teste
        metrics: Métricas agregadas da bateria
        metrics_by_tag: Métricas agregadas por tag
        metrics_by_group: Métricas agregadas por grupo de tools
        conjunto: Escopo da bateria ("todos", "grupo:<g>" ou "pergunta:<id>");
            None em baterias antigas
    """

    batch_id: str
    timestamp: str
    mcp_version: str
    git_commit_sha: str
    environment: str
    total_tests: int
    passed: int
    partial: int  # MCP ok but validation failed
    failed: int
    skipped: int
    timeout: int
    test_results: list[TestResult]
    metrics: BatchMetrics
    metrics_by_tag: dict[str, TagMetrics]
    metrics_by_group: dict[str, GroupMetrics]
    conjunto: str | None = None
