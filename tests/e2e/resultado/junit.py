"""Saída JUnit dos registros, para os painéis de CI."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

from tests.e2e.resultado.modelos import Registro

_INVALIDOS_XML = re.compile("[^\t\n\r\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")
_TAG_POR_ESTADO = {"falhou": "failure", "erro_infra": "error", "pulado": "skipped"}


def escrever_junit(registros: Iterable[Registro], destino: Path) -> Path:
    lista = list(registros)
    suite = ET.Element(
        "testsuite",
        name="bateria",
        tests=str(len(lista)),
        failures=str(sum(r.estado == "falhou" for r in lista)),
        errors=str(sum(r.estado == "erro_infra" for r in lista)),
        skipped=str(sum(r.estado == "pulado" for r in lista)),
        time=f"{sum(r.duracao_s for r in lista):.3f}",
    )
    for r in lista:
        caso = ET.SubElement(
            suite,
            "testcase",
            classname=f"{r.conjunto}.{r.agente}.{r.config}",
            name=f"{r.caso}[{r.repeticao}]",
            time=f"{r.duracao_s:.3f}",
        )
        tag = _TAG_POR_ESTADO.get(r.estado)
        if tag:
            ET.SubElement(caso, tag, message=_INVALIDOS_XML.sub("\ufffd", r.motivo))
    destino.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(destino, encoding="utf-8", xml_declaration=True)
    return destino
