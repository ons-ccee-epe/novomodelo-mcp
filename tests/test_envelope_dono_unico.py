"""`adapters/envelope.py` é o único módulo que monta um envelope de erro.

Varre a AST de `src/novomodelo_mcp`: fora do dono, nenhum dict literal, `dict(...)`,
`.update(...)` ou atribuição `x["status"] = ...` pode pôr `"error"` em `status`.
"""

import ast
from pathlib import Path

import novomodelo_mcp
from novomodelo_mcp.adapters import envelope

_PACKAGE = Path(novomodelo_mcp.__file__).parent
_OWNER = _PACKAGE / "adapters" / "envelope.py"


def _can_be_error(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Constant) and n.value == "error" for n in ast.walk(node))


def _hand_built_errors(source: str) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            hit = any(
                isinstance(k, ast.Constant) and k.value == "status" and _can_be_error(v)
                for k, v in zip(node.keys, node.values, strict=True)
            )
        elif isinstance(node, ast.Call):
            hit = any(kw.arg == "status" and _can_be_error(kw.value) for kw in node.keywords)
        elif isinstance(node, ast.Assign):
            hit = _can_be_error(node.value) and any(
                isinstance(t, ast.Subscript)
                and isinstance(t.slice, ast.Constant)
                and t.slice.value == "status"
                for t in node.targets
            )
        else:
            hit = False
        if hit:
            lines.append(node.lineno)
    return lines


def test_so_o_envelope_monta_envelope_de_erro():
    found = {
        f"{path.relative_to(_PACKAGE).as_posix()}:{line}"
        for path in _PACKAGE.rglob("*.py")
        if path != _OWNER
        for line in _hand_built_errors(path.read_text(encoding="utf-8"))
    }
    assert not found, f"use envelope.error/as_error em vez de montar o envelope: {sorted(found)}"


def test_varredura_acusa_cada_forma_de_montar_a_mao():
    source = (
        'a = {"status": "error", "diagnostics": []}\n'
        'b = {"status": "ok" if ok else "error"}\n'
        'c = dict(status="error")\n'
        'd.update(status="error")\n'
        'e["status"] = "error"\n'
        'f = {"status": "ok", "exit_code": 0}\n'
    )
    assert sorted(_hand_built_errors(source)) == [1, 2, 3, 4, 5]


def test_dono_trunca_mensagem_e_detalhe_e_sempre_poe_exit_code():
    longo = "x" * (envelope.MAX_DETAIL_CHARS + 10)
    env = envelope.error(7, longo, longo, extra=1)
    assert env["exit_code"] == 7 and env["extra"] == 1
    assert [len(d) for d in env["diagnostics"]] == [envelope.MAX_DETAIL_CHARS] * 2
    exc = envelope.as_error(ValueError(longo), code=3)
    assert exc["status"] == "error" and exc["exit_code"] == 3
    assert len(exc["diagnostics"][0]) == envelope.MAX_DETAIL_CHARS
