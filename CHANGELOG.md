# Changelog

As mudanças do novomodelo-mcp que alguém usando o servidor percebe ficam neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e o
projeto adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/). O MCP
`X.Y.Z` pareia com o novomodelo `X.Y.Z` e com o novomodelo-bridge `X.Y.Z`; uma correção
só do MCP vira `X.Y.Z.postN`.

## [Unreleased]

### Changed

- As respostas das tools do bridge cabem no teto `NOVOMODELO_MCP_MAX_RESPONSE_KB`: as tabelas
  dos diagnósticos perdem as últimas linhas, a maior tabela primeiro, e todo diagnóstico
  continua na resposta. Cada tabela cortada traz `truncado` e `linhas_total`, e a resposta
  traz `cortado_por_tamanho`. Só quando cortar as tabelas não basta a lista de diagnósticos
  é cortada.

## [0.20.0] - 2026-11-04

### Changed

- O MCP pareia com o novomodelo 0.20.0 e o novomodelo-bridge 0.20.0. As docs embutidas
  são as da 0.20.0, e as páginas `changelog/novomodelo` e `changelog/novomodelo-bridge`
  trazem a seção da 0.20.0.

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
