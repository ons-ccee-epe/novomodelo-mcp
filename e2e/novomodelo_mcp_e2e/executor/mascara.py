"""Máscara de segredos aplicada antes de qualquer gravação em disco."""

from __future__ import annotations

import re
from collections.abc import Iterable

_PADROES = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-~+/=]+"),
    re.compile(
        r"(?i)((?:token|api[_-]?key|authorization)\"?\s*[:=]\s*\"?)[A-Za-z0-9._\-~+/=]{12,}"
    ),
]
MASCARA = "***"


def mascarar(texto: str, segredos: Iterable[str] = ()) -> str:
    for s in sorted((s for s in segredos if s and len(s) >= 8), key=len, reverse=True):
        texto = texto.replace(s, MASCARA)
    for padrao in _PADROES:
        texto = padrao.sub(lambda m: (m.group(1) if m.groups() else "") + MASCARA, texto)
    return texto
