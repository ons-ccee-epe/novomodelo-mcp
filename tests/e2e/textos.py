"""Tratamento de texto compartilhado pela bateria."""

from __future__ import annotations

import re
from pathlib import Path

_INICIO_CAMINHO = r"(?:[A-Za-z]:[\\/]|\\\\|/(?!/))"
_CAMINHO_ENTRE_ASPAS = re.compile(rf"'{_INICIO_CAMINHO}[^']*'|\"{_INICIO_CAMINHO}[^\"]*\"")
_CAMINHO_ABSOLUTO = re.compile(
    rf"(?<![\w.~/\\-]){_INICIO_CAMINHO}[^\s'\"]*"
    r"(?:(?: [^\s'\"/\\]+)* [^\s'\"]*[/\\][^\s'\"]*)*"
)


def sem_caminhos(texto: str, conhecidos: tuple[Path, ...] = ()) -> str:
    for caminho in sorted({str(c) for c in conhecidos if str(c) not in ("", ".")}, key=len)[::-1]:
        texto = texto.replace(caminho, "<caminho>")
    texto = _CAMINHO_ENTRE_ASPAS.sub("<caminho>", texto)
    return _CAMINHO_ABSOLUTO.sub("<caminho>", texto)
