"""Persistência de métricas de execução em formato JSONL."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .models import ExecutionResult, MetricRecord


class MetricStore:
    """Armazena métricas de execução em arquivo JSONL (append-only).

    Uso:
        store = MetricStore()  # usa path padrão ou NOVOMODELO_MCP_METRICS_PATH
        store.append(result, environment="local")
        history = store.read_all()
    """

    DEFAULT_PATH = Path(__file__).parent.parent / "metrics" / "history.jsonl"

    def __init__(self, path: Path | str | None = None) -> None:
        """Inicializa o store.

        Args:
            path: Caminho do arquivo JSONL. Se None, usa env var
                  NOVOMODELO_MCP_METRICS_PATH ou path padrão.
        """
        if path is not None:
            self.path = Path(path)
        else:
            env_path = os.environ.get("NOVOMODELO_MCP_METRICS_PATH")
            if env_path:
                self.path = Path(env_path)
            else:
                self.path = self.DEFAULT_PATH

        self._version: str | None = None
        self._git_sha: str | None = None

    def append(
        self,
        result: ExecutionResult,
        environment: str = "local",
    ) -> None:
        """Persiste resultado de execução como nova linha JSONL.

        Args:
            result: Resultado da execução do teste
            environment: "local" ou URL do servidor
        """
        record = MetricRecord.from_execution_result(
            result,
            environment=environment,
            version=self._get_version(),
            git_sha=self._get_git_sha(),
        )

        self._ensure_parent_exists()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def append_batch(
        self,
        results: list[ExecutionResult],
        environment: str = "local",
    ) -> None:
        """Persiste múltiplos resultados de uma vez.

        Args:
            results: Lista de resultados
            environment: "local" ou URL do servidor
        """
        if not results:
            return

        version = self._get_version()
        git_sha = self._get_git_sha()

        self._ensure_parent_exists()
        with open(self.path, "a", encoding="utf-8") as f:
            for result in results:
                record = MetricRecord.from_execution_result(
                    result,
                    environment=environment,
                    version=version,
                    git_sha=git_sha,
                )
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

    def read_all(self) -> list[MetricRecord]:
        """Lê todo o histórico de métricas.

        Returns:
            Lista de MetricRecord ordenada por timestamp (mais antigo primeiro).
        """
        if not self.path.exists():
            return []

        records = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(MetricRecord.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    # Ignora linhas inválidas
                    continue

        return records

    def read_last_run(self) -> list[MetricRecord]:
        """Lê apenas os registros do último run (mesmo timestamp base).

        Returns:
            Lista de MetricRecord do último run.
        """
        all_records = self.read_all()
        if not all_records:
            return []

        # Agrupa por git_sha + timestamp (mesmo minuto = mesmo run)
        last_sha = all_records[-1].git_commit_sha
        last_records = []

        for record in reversed(all_records):
            if record.git_commit_sha == last_sha:
                last_records.append(record)
            else:
                break

        return list(reversed(last_records))

    def count(self) -> int:
        """Retorna número total de registros."""
        return len(self.read_all())

    def clear(self) -> None:
        """Remove todo o histórico (use com cuidado!)."""
        if self.path.exists():
            self.path.unlink()

    def _ensure_parent_exists(self) -> None:
        """Cria diretório pai se não existir."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _get_version(self) -> str:
        """Obtém versão do pacote novomodelo-mcp."""
        if self._version is None:
            try:
                from importlib.metadata import version

                self._version = version("novomodelo-mcp")
            except Exception:
                self._version = "unknown"
        return self._version

    def _get_git_sha(self) -> str:
        """Obtém SHA do commit atual via git."""
        if self._git_sha is None:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=Path(__file__).parent,
                )
                if result.returncode == 0:
                    self._git_sha = result.stdout.strip()
                else:
                    self._git_sha = "unknown"
            except Exception:
                self._git_sha = "unknown"
        return self._git_sha
