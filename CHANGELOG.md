# Changelog

As mudanças do novomodelo-mcp que alguém usando o servidor percebe ficam neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e o
projeto adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/). O MCP
`X.Y.Z` pareia com o novomodelo `X.Y.Z` e com o novomodelo-bridge `X.Y.Z`; uma correção
só do MCP vira `X.Y.Z.postN`.

## [Unreleased]

### Changed

- O MCP declara suporte a Python 3.12, 3.13 e 3.14, e a CI testa cada versão em Linux
  (x86_64 e aarch64), macOS (Apple Silicon e Intel) e Windows (x86_64).

### Fixed

- No macOS Intel, o MCP instala o cryptography 48, a última versão com wheel para esse
  alvo, em vez de compilar o 50 na instalação.
