"""Moldagem de saída: garante que nenhuma resposta estoure o contexto do agente."""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import Settings


def attach_artifact(envelope: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    """Registra o CAMINHO de um artefato grande gerado (deck, HTML), nunca o conteúdo."""
    envelope.setdefault("artifacts", {})[key] = path
    return envelope


def attach_version_warnings(result: Any, warnings: list[str]) -> Any:
    """Acrescenta `avisos_de_versao` a uma resposta dict quando há peça divergente."""
    if warnings and isinstance(result, dict):
        result["avisos_de_versao"] = warnings
    return result


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


_VARIABLE_PARTS = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`|\d+(?:\.\d+)?")


def group_diagnostics(items: list[Any], max_groups: int,
                      max_examples: int = 3) -> dict[str, Any]:
    """Agrupa diagnósticos por `kind` + mensagem sem números e trechos entre aspas.

    Só conta, nada some: somados todos os grupos (antes do teto `max_groups`), os
    `count` dão `total`.
    """
    groups: dict[tuple[Any, str], dict[str, Any]] = {}
    for item in items:
        if isinstance(item, dict):
            kind, message = item.get("kind"), str(item.get("message", ""))
        else:
            kind, message = None, str(item)
        template = _VARIABLE_PARTS.sub("…", message)
        group = groups.setdefault((kind, template), {
            "kind": kind, "mensagem_modelo": template, "count": 0, "exemplos": []})
        group["count"] += 1
        if len(group["exemplos"]) < max_examples:
            group["exemplos"].append(item)
    ordered = sorted(groups.values(), key=lambda g: (-g["count"], str(g["kind"])))
    return {"grupos": ordered[:max_groups], "total": len(items),
            "grupos_total": len(ordered), "grupos_truncados": len(ordered) > max_groups}
