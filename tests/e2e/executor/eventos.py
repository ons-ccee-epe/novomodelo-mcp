"""Eventos normalizados a partir do log de cada agente.

O log gravado pelo executor tem uma linha JSON por evento do agente, embrulhada com o
instante de chegada: {"t": <segundos desde o início>, "evento": <linha original>}.
Uma linha sem embrulho (log cru) vale com `t` igual ao do evento anterior.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

Tipo = Literal["tool", "resultado_tool", "negacao", "texto", "fim"]
PREFIXO_MCP = "mcp__novomodelo__"


@dataclass(frozen=True)
class Evento:
    tipo: Tipo
    nome: str | None
    args: dict
    t: float
    erro: bool = False
    dados: dict = field(default_factory=dict)

    @property
    def do_mcp(self) -> bool:
        return bool(self.dados.get("mcp"))


@dataclass
class Leitura:
    eventos: list[Evento]
    linhas_invalidas: int = 0


def _desembrulhar(linha: str, t_anterior: float) -> tuple[float, dict] | None:
    try:
        obj = json.loads(linha)
    except ValueError:
        return None
    if isinstance(obj, dict) and "evento" in obj and "t" in obj:
        return float(obj["t"]), obj["evento"]
    return t_anterior, obj


def _nome_tool(nome: str) -> tuple[str, bool]:
    if nome.startswith(PREFIXO_MCP):
        return nome[len(PREFIXO_MCP) :], True
    return nome, False


def ler_claude(linhas: Iterable[str]) -> Leitura:
    eventos: list[Evento] = []
    nomes_por_id: dict[str, tuple[str, bool]] = {}
    negados: set[str] = set()
    invalidas, t = 0, 0.0
    for linha in linhas:
        if not linha.strip():
            continue
        lido = _desembrulhar(linha, t)
        if lido is None or not isinstance(lido[1], dict):
            invalidas += 1
            continue
        t, obj = lido
        tipo = obj.get("type")
        mensagem = obj.get("message")
        conteudo = mensagem.get("content") if isinstance(mensagem, dict) else None
        if tipo == "system" and obj.get("subtype") == "permission_denied":
            ident = obj.get("tool_use_id", "")
            if ident not in negados:
                negados.add(ident)
                nome, mcp = _nome_tool(obj.get("tool_name", ""))
                eventos.append(Evento("negacao", nome, {}, t, dados={"mcp": mcp}))
            continue
        if tipo == "assistant" and isinstance(conteudo, list):
            for bloco in conteudo:
                if bloco.get("type") == "tool_use":
                    nome, mcp = _nome_tool(bloco.get("name", ""))
                    nomes_por_id[bloco.get("id", "")] = (nome, mcp)
                    eventos.append(
                        Evento("tool", nome, bloco.get("input") or {}, t, dados={"mcp": mcp})
                    )
                elif bloco.get("type") == "text":
                    eventos.append(
                        Evento("texto", None, {}, t, dados={"texto": bloco.get("text", "")})
                    )
        elif tipo == "user" and isinstance(conteudo, list):
            for bloco in conteudo:
                if bloco.get("type") == "tool_result":
                    nome, mcp = nomes_por_id.get(bloco.get("tool_use_id", ""), (None, False))
                    eventos.append(
                        Evento(
                            "resultado_tool",
                            nome,
                            {},
                            t,
                            erro=bool(bloco.get("is_error")),
                            dados={"mcp": mcp, "conteudo": _texto(bloco.get("content"))},
                        )
                    )
        elif tipo == "result":
            for negada in obj.get("permission_denials") or []:
                if negada.get("tool_use_id", "") in negados:
                    continue
                nome, mcp = _nome_tool(negada.get("tool_name", ""))
                eventos.append(
                    Evento("negacao", nome, negada.get("tool_input") or {}, t, dados={"mcp": mcp})
                )
            uso = obj.get("usage") or {}
            eventos.append(
                Evento(
                    "fim",
                    None,
                    {},
                    t,
                    erro=bool(obj.get("is_error")),
                    dados={
                        "resposta": obj.get("result") or "",
                        "duracao_s": (obj.get("duration_ms") or 0) / 1000,
                        "tokens_entrada": sum(
                            int(uso.get(k) or 0)
                            for k in (
                                "input_tokens",
                                "cache_creation_input_tokens",
                                "cache_read_input_tokens",
                            )
                        ),
                        "tokens_saida": int(uso.get("output_tokens") or 0),
                    },
                )
            )
    return Leitura(eventos, invalidas)


def _texto(conteudo) -> str:
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        return "\n".join(str(b.get("text", "")) for b in conteudo if isinstance(b, dict))
    return ""


_PREFIXOS_KIRO = ("@novomodelo/", "novomodelo___", "novomodelo/", PREFIXO_MCP)
_NATIVAS_KIRO = {
    "execute": "Bash",
    "shell": "Bash",
    "execute_bash": "Bash",
    "read": "Read",
    "fs_read": "Read",
    "search": "Grep",
    "grep": "Grep",
    "glob": "Glob",
    "web_search": "WebSearch",
    "web_fetch": "WebFetch",
    "edit": "Write",
    "write": "Write",
    "fs_write": "Write",
}
_NEGADA_KIRO = "Permission request failed"


def _nome_kiro(chamada: dict) -> tuple[str, bool]:
    meta = (chamada.get("_meta") or {}).get("kiro") or {}
    if meta.get("mcpServerName") and meta.get("toolName"):
        return str(meta["toolName"]), True
    if meta.get("toolName") in _NATIVAS_KIRO:
        return _NATIVAS_KIRO[meta["toolName"]], False
    titulo = str(chamada.get("title") or chamada.get("kind") or "").removeprefix("Running: ")
    origem = str(meta.get("toolOrigin") or "default")
    for prefixo in _PREFIXOS_KIRO:
        if titulo.startswith(prefixo):
            return titulo[len(prefixo) :], True
    if origem not in ("default", "builtin"):
        return titulo, True
    # Nome equivalente do Claude: o validador de uso de tools nativas é um só para os dois agentes.
    return _NATIVAS_KIRO.get(str(chamada.get("kind") or ""), titulo), False


def ler_kiro(linhas: Iterable[str]) -> Leitura:
    """Eventos ACP do `kiro-cli chat --output-format stream-json`."""
    eventos: list[Evento] = []
    por_id: dict[str, tuple[str, bool]] = {}
    invalidas, t = 0, 0.0
    for linha in linhas:
        if not linha.strip():
            continue
        lido = _desembrulhar(linha, t)
        if lido is None or not isinstance(lido[1], dict):
            invalidas += 1
            continue
        t, obj = lido
        tipo, dados = obj.get("type"), obj.get("data") or {}
        if tipo == "sessionUpdate":
            u = dados.get("update") or {}
            qual = u.get("sessionUpdate")
            ident = u.get("toolCallId", "")
            if qual == "tool_call" and ident not in por_id:
                por_id[ident] = _nome_kiro(u)
                nome, mcp = por_id[ident]
                eventos.append(Evento("tool", nome, u.get("rawInput") or {}, t, dados={"mcp": mcp}))
            elif qual == "tool_call_update" and u.get("status") in ("completed", "failed"):
                nome, mcp = por_id.get(ident, (None, False))
                texto = "\n".join(
                    str((c.get("content") or {}).get("text", ""))
                    for c in u.get("content") or []
                    if isinstance(c, dict)
                )
                if u.get("status") == "failed" and texto.startswith(_NEGADA_KIRO):
                    eventos.append(Evento("negacao", nome, {}, t, dados={"mcp": mcp}))
                    continue
                eventos.append(
                    Evento(
                        "resultado_tool",
                        nome,
                        {},
                        t,
                        erro=u.get("status") == "failed",
                        dados={"mcp": mcp, "conteudo": texto},
                    )
                )
        elif tipo in ("permissionRequest", "requestPermission", "permissionDenied"):
            nome, mcp = _nome_kiro(dados.get("toolCall") or dados)
            eventos.append(Evento("negacao", nome, {}, t, dados={"mcp": mcp}))
        elif tipo == "runFinished":
            eventos.append(
                Evento(
                    "fim",
                    None,
                    {},
                    t,
                    erro=dados.get("status") != "success",
                    dados={
                        "resposta": dados.get("finalText") or "",
                        "duracao_s": t,
                        "tokens_entrada": 0,
                        "tokens_saida": 0,
                    },
                )
            )
    return Leitura(eventos, invalidas)
