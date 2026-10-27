"""Opções da suíte: o que depende do ambiente só roda quando pedido.

Por padrão a suíte é offline e usa os binários falsos. Um teste marcado com
`executaveis_reais` (o `novomodelo` e o `novomodelo-bridge` instalados) ou com `rede`
(domínios oficiais) é pulado, com o motivo, a menos que a opção correspondente seja
passada; com a opção, a falta do executável ou da rede vira falha do teste.
"""

from __future__ import annotations

import pytest

pytest_plugins = ("pytester",)

OPCOES = {
    "executaveis_reais": "--executaveis-reais",
    "rede": "--com-rede",
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--executaveis-reais",
        action="store_true",
        default=False,
        help="roda os testes com o novomodelo e o novomodelo-bridge instalados",
    )
    parser.addoption(
        "--com-rede",
        action="store_true",
        default=False,
        help="roda os testes que acessam a rede (domínios oficiais)",
    )
    grupo = parser.getgroup("executaveis_reais", "ponta a ponta (com --executaveis-reais)")
    grupo.addoption(
        "--mcp-instalado",
        nargs="?",
        const="",
        default=None,
        metavar="CAMINHO",
        help="sobe o novomodelo-mcp instalado (PATH ou CAMINHO) em vez do código-fonte",
    )
    grupo.addoption(
        "--instalar-executavel",
        action="store_true",
        default=False,
        help="antes da bateria, instala o executável pela tool instalar_novomodelo",
    )
    grupo.addoption(
        "--bridge-repo",
        metavar="PASTA",
        help="clone do novomodelo-bridge: usa os decks mínimos públicos de tests/decks/",
    )
    grupo.addoption("--newave-src", metavar="PASTA", help="caso NEWAVE próprio")
    grupo.addoption("--decomp-src", metavar="PASTA", help="caso DECOMP próprio")
    grupo.addoption(
        "--claude-code",
        action="store_true",
        default=False,
        help="confere, com o Claude Code em modo não interativo, a aprovação das tools",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for marcador, opcao in OPCOES.items():
        if config.getoption(opcao):
            continue
        pular = pytest.mark.skip(reason=f"precisa de {opcao}")
        for item in items:
            if marcador in item.keywords:
                item.add_marker(pular)
