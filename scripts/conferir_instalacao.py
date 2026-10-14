"""Confere um MCP instalado: sobe o executável por stdio, como um cliente faria.

Uso: conferir_instalacao.py --versao 0.18.0 [--server-info] -- <comando do MCP>

Confere que o `initialize` anuncia a versão esperada e que as tools aparecem. Com
`--server-info`, também chama o `server_info` (usa a rede para a versão nova) e confere
a versão do MCP e as docs embutidas. Só biblioteca padrão: roda fora do checkout.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


class Falha(Exception):
    pass


def _sessao(cmd: list[str]):
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8", errors="replace")
    ids = iter(range(1, 1000))

    def pedir(method: str, params: dict | None = None) -> dict:
        req_id = next(ids)
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method,
                                     "params": params or {}}) + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                raise Falha(f"o servidor fechou a saída ({method}): {proc.stderr.read()[-2000:]}")
            msg = json.loads(line)
            if msg.get("id") == req_id:
                if "error" in msg:
                    raise Falha(f"{method}: {msg['error']}")
                return msg["result"]

    def avisar(method: str) -> None:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        proc.stdin.flush()

    return proc, pedir, avisar


def conferir(cmd: list[str], versao: str, server_info: bool) -> list[str]:
    proc, pedir, avisar = _sessao(cmd)
    linhas = []
    try:
        init = pedir("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "conferir_instalacao", "version": "1"}})
        avisar("notifications/initialized")
        anunciada = init["serverInfo"]["version"]
        if anunciada != versao:
            raise Falha(f"initialize anuncia {anunciada}, esperada {versao}")
        linhas.append(f"initialize: {init['serverInfo']['name']} {anunciada}")
        tools = [t["name"] for t in pedir("tools/list")["tools"]]
        if "server_info" not in tools:
            raise Falha(f"server_info não está entre as tools: {tools}")
        linhas.append(f"tools/list: {len(tools)} tools")
        if server_info:
            res = pedir("tools/call", {"name": "server_info", "arguments": {}})
            info = json.loads(res["content"][0]["text"])
            if info.get("versao_mcp") != versao:
                raise Falha(f"server_info.versao_mcp = {info.get('versao_mcp')}, esperada {versao}")
            if info.get("docs", {}).get("origem") != "embutidas":
                raise Falha(f"docs não são as embutidas: {info.get('docs')}")
            pecas = info.get("versoes", {})
            linhas.append("server_info: " + ", ".join(
                f"{k} {v.get('versao')}" for k, v in pecas.items() if isinstance(v, dict)))
            linhas += [f"aviso: {a}" for a in info.get("avisos_de_versao", [])]
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return linhas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--versao", required=True)
    parser.add_argument("--server-info", action="store_true")
    parser.add_argument("comando", nargs="+")
    args = parser.parse_args(argv)
    try:
        for linha in conferir(args.comando, args.versao, args.server_info):
            print(linha)
    except (Falha, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FALHOU: {exc}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
