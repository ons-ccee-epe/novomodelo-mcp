"""Moldagem de saída: garante que nenhuma resposta estoure o contexto do agente."""
from __future__ import annotations

import json
from typing import Any

from ..config import Settings


def attach_artifact(envelope: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    """Registra o CAMINHO de um artefato grande gerado (deck, HTML), nunca o conteúdo."""
    envelope.setdefault("artifacts", {})[key] = path
    return envelope


def cap_envelope(envelope: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Trunca listas de diagnóstico longas e sinaliza summary grande demais.

    Não altera status nem exit_code — só o volume de texto devolvido.
    """
    diags = envelope.get("diagnostics")
    if isinstance(diags, list) and len(diags) > settings.max_diagnostics:
        omitted = len(diags) - settings.max_diagnostics
        envelope["diagnostics"] = diags[: settings.max_diagnostics] + [
            f"... (+{omitted} diagnósticos omitidos; ver arquivos/relatório)"
        ]

    summary = envelope.get("summary")
    if summary is not None:
        try:
            size = len(json.dumps(summary, ensure_ascii=False))
        except (TypeError, ValueError):
            size = 0
        if size > settings.max_summary_chars:
            envelope["summary_truncated"] = True
            envelope["summary_note"] = (
                f"summary com ~{size} chars excede o teto "
                f"({settings.max_summary_chars}); consulte os artefatos gerados."
            )
    return envelope
