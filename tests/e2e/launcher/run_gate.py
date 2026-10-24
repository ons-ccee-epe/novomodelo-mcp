"""Trava de "um run por vez", compartilhada pelos runs de agente e de carga.

Cada run sobe uma árvore de processos (agente + servidor MCP, ou N servidores);
dois ao mesmo tempo esgotam a máquina e falseiam as medições um do outro.
"""
from __future__ import annotations

import threading

__all__ = ["RunAlreadyActiveError", "RunGate"]


class RunAlreadyActiveError(RuntimeError):
    """Já existe um run (de agente ou de carga) pendente ou rodando."""


class RunGate:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owner: str | None = None

    @property
    def owner(self) -> str | None:
        with self._lock:
            return self._owner

    def acquire(self, owner: str) -> None:
        """Reserva a vaga para ``owner``.

        Raises:
            RunAlreadyActiveError: Se outro run ainda não liberou a vaga.
        """
        with self._lock:
            if self._owner is not None:
                raise RunAlreadyActiveError(f"run {self._owner} ainda em andamento")
            self._owner = owner

    def release(self, owner: str) -> None:
        """Libera a vaga; idempotente e ignorada se ``owner`` não é o dono atual."""
        with self._lock:
            if self._owner == owner:
                self._owner = None
