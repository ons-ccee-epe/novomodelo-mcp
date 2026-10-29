#!/usr/bin/env python3
"""check_termos_proibidos.py — termos que não entram no repositório público.

Lê os padrões de ``termos_proibidos.toml`` e, se existir, a lista interna do arquivo
apontado por ``NOVOMODELO_TERMOS_INTERNOS`` (uma expressão por linha, ``#`` comenta,
sem distinção de caixa). A lista interna nunca fica no repositório.

Sem opções olha os arquivos versionados. ``--desde <ref>`` olha o conteúdo adicionado
nos commits ``<ref>..HEAD``; ``--historico`` olha todos os commits, sem os padrões da
seção ``[historico]`` do TOML; ``--mensagens`` inclui as mensagens dos commits nesses
dois modos.

Saída: ``arquivo:linha: <padrão>`` (``interno #<n>`` para a lista interna), nunca o
trecho. Código de saída 0 limpo, 1 achados, 2 erro de uso.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

RAIZ_PADRAO = Path(__file__).resolve().parents[2]
TOML_PADRAO = Path(__file__).with_name("termos_proibidos.toml")
VARIAVEL_INTERNOS = "NOVOMODELO_TERMOS_INTERNOS"
HUNK = re.compile(r"^(@@+) .* \+(\d+)(?:,\d+)? @@+")


@dataclass(frozen=True)
class Padrao:
    nome: str
    regex: re.Pattern[str]
    escopo: tuple[str, ...] = ()


def carregar_padroes(
    toml: Path,
) -> tuple[list[Padrao], dict[str, frozenset[str]], frozenset[str]]:
    dados = tomllib.loads(toml.read_text(encoding="utf-8"))
    padroes = []
    for item in dados.get("padroes", []):
        texto = bytes.fromhex(item["hex"]).decode() if "hex" in item else item["regex"]
        flags = 0 if item.get("sensivel_a_caixa") else re.IGNORECASE
        padroes.append(
            Padrao(item["nome"], re.compile(texto, flags), tuple(item.get("escopo", ())))
        )
    permitidos = {
        caminho: frozenset(regra["padroes"])
        for caminho, regra in dados.get("permitidos", {}).items()
    }
    ignorados = frozenset(dados.get("historico", {}).get("ignora", ()))
    return padroes, permitidos, ignorados


class ListaInternaInvalida(Exception):
    """A lista interna está configurada, mas não pôde ser usada."""


def carregar_internos(caminho: str | None) -> list[Padrao]:
    if not caminho or not caminho.strip():
        return []
    try:
        linhas = Path(caminho).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as erro:
        raise ListaInternaInvalida("a lista interna configurada não pôde ser lida") from erro
    padroes = []
    for n, linha in enumerate(linhas, 1):
        texto = linha.strip()
        if not texto or texto.startswith("#"):
            continue
        try:
            padroes.append(Padrao(f"interno #{n}", re.compile(texto, re.IGNORECASE)))
        except re.error:
            raise ListaInternaInvalida(
                f"expressão inválida na linha {n} da lista interna"
            ) from None
    return padroes


def casar(
    caminho: str,
    linha: str,
    padroes: list[Padrao],
    permitidos: dict[str, frozenset[str]],
) -> list[str]:
    liberados = frozenset().union(
        *(
            nomes
            for p, nomes in permitidos.items()
            if caminho == p or (p.endswith("/") and caminho.startswith(p))
        )
    )
    return [
        p.nome
        for p in padroes
        if (p.nome.startswith("interno #") or p.nome not in liberados)
        and (not p.escopo or caminho.startswith(p.escopo))
        and p.regex.search(linha)
    ]


def _git(raiz: Path, *args: str) -> str:
    res = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=raiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if res.returncode != 0:
        sys.exit(f"erro: git {args[0]} falhou")
    return res.stdout


def achados_da_arvore(raiz, padroes, permitidos):
    for caminho in _git(raiz, "ls-files").split("\n"):
        arquivo = raiz / caminho
        if not caminho or not arquivo.is_file():
            continue
        bruto = arquivo.read_bytes()
        if b"\x00" in bruto:
            continue
        for n, linha in enumerate(bruto.decode("utf-8", errors="replace").split("\n"), 1):
            for nome in casar(caminho, linha, padroes, permitidos):
                yield f"{caminho}:{n}: {nome}"


def achados_dos_commits(raiz, intervalo, mensagens, padroes, permitidos):
    saida = _git(
        raiz, "log", "-p", "-U0", "--cc", "--no-prefix", "--no-color", "--format=%x00%H", *intervalo
    )
    caminho, n, colunas, commit, em_trecho = "", 0, 1, "", False
    for linha in saida.split("\n"):
        if linha.startswith("\x00"):
            commit, caminho, em_trecho = linha[1:8], "", False
        elif linha.startswith("diff "):
            caminho, em_trecho = "", False
        elif not em_trecho:
            if linha.startswith("+++ "):
                destino = linha[4:]
                caminho = "" if destino == "/dev/null" else destino
            elif m := HUNK.match(linha):
                em_trecho, colunas, n = True, len(m.group(1)) - 1, int(m.group(2)) - 1
        elif m := HUNK.match(linha):
            colunas, n = len(m.group(1)) - 1, int(m.group(2)) - 1
        elif linha.startswith("\\") or not caminho:
            continue
        else:
            marca = linha[:colunas]
            if "-" in marca:
                continue
            n += 1
            if marca == "+" * colunas:
                for nome in casar(caminho, linha[colunas:], padroes, permitidos):
                    yield f"{caminho}:{n}: {nome} ({commit})"
    if mensagens:
        bruto = _git(raiz, "log", "--format=%x00%h%x01%B", *intervalo)
        for bloco in bruto.split("\x00")[1:]:
            curto, _, corpo = bloco.partition("\x01")
            for linha in corpo.split("\n"):
                for nome in casar("", linha, padroes, {}):
                    yield f"commit {curto}:mensagem: {nome}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    grupo = ap.add_mutually_exclusive_group()
    grupo.add_argument("--desde", metavar="REF", help="só os commits REF..HEAD")
    grupo.add_argument("--historico", action="store_true", help="todos os commits")
    ap.add_argument("--mensagens", action="store_true", help="inclui mensagens de commit")
    ap.add_argument("--raiz", type=Path, default=RAIZ_PADRAO)
    ap.add_argument("--toml", type=Path, default=TOML_PADRAO)
    args = ap.parse_args(argv)

    padroes, permitidos, ignorados = carregar_padroes(args.toml)
    if args.historico:
        padroes = [p for p in padroes if p.nome not in ignorados]
    try:
        padroes += carregar_internos(os.environ.get(VARIAVEL_INTERNOS))
    except ListaInternaInvalida as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 2
    if args.desde:
        achados = achados_dos_commits(
            args.raiz, [f"{args.desde}..HEAD"], args.mensagens, padroes, permitidos
        )
    elif args.historico:
        achados = achados_dos_commits(args.raiz, ["HEAD"], args.mensagens, padroes, permitidos)
    else:
        achados = achados_da_arvore(args.raiz, padroes, permitidos)

    lista = list(achados)
    for achado in lista:
        print(achado)
    if lista:
        por_padrao = Counter(re.sub(r"^.*?: ([^:()]+?)(?: \(\w+\))?$", r"\1", a) for a in lista)
        resumo = ", ".join(f"{nome}={n}" for nome, n in sorted(por_padrao.items()))
        print(f"{len(lista)} achado(s): {resumo}", file=sys.stderr)
        return 1
    print("OK: nenhum termo proibido")
    return 0


if __name__ == "__main__":
    sys.exit(main())
