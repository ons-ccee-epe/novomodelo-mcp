# Changelog

As mudanças do novomodelo-mcp que alguém usando o servidor percebe ficam neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e o
projeto adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/). O MCP
`X.Y.Z` pareia com o novomodelo `X.Y.Z` e com o novomodelo-bridge `X.Y.Z`; uma correção
só do MCP vira `X.Y.Z.postN`.

## [Unreleased]

### Changed

- As versões mínimas das dependências passam a ser as que a CI testa: mcp 1.30.0,
  polars 2.1.0, jsonschema 4.26.0, duckdb 2.0.0 e truststore 0.10.5. As mínimas
  anteriores não instalavam um servidor funcional (o mcp antes da 1.11 nem importa com o
  pydantic atual).

### Fixed

- Toda resposta de erro traz `exit_code` e `diagnostics`. Alguns erros do `deck_edit_json`,
  do `deck_edit_parquet`, do `schema_get` e do `docs_read` vinham sem `exit_code`, e a
  validação reprovada do `case_validate` vinha sem `diagnostics`.

## [0.19.1] - 2026-10-28

### Changed

- O MCP pareia com o novomodelo 0.19.1 e o novomodelo-bridge 0.19.1. As docs embutidas
  são as da 0.19.1, e as páginas `changelog/novomodelo` e `changelog/novomodelo-bridge`
  trazem a seção da 0.19.1.
- O MCP é instalado e atualizado pelo PyPI: `uv tool install novomodelo-mcp`. Os avisos
  de versão dão o comando `uv tool install --force --compile-bytecode novomodelo-mcp==X.Y.Z`, e o
  `server_info` também procura no PyPI uma versão nova do próprio MCP, com o link das
  notas no repositório `ons-ccee-epe/novomodelo-mcp`.
- O MCP declara suporte a Python 3.12, 3.13 e 3.14, e a CI testa cada versão em Linux
  (x86_64 e aarch64), macOS (Apple Silicon e Intel) e Windows (x86_64).

### Fixed

- No Windows, as tools que carregam uma biblioteca nativa, como o `deck_sql` e o
  `results_stochastic`, não travam mais à espera de uma nova mensagem do cliente.
- No macOS Intel, o MCP instala o cryptography 48, a última versão com wheel para esse
  alvo, em vez de compilar o 50 na instalação.
- No Windows com Python 3.13 ou 3.14, a guarda de pasta recusa um caminho com caractere
  NUL, como nos outros alvos, em vez de deixá-lo passar.
