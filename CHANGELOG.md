# Changelog

As mudanças do novomodelo-mcp que alguém usando o servidor percebe ficam neste arquivo.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e o
projeto adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/). O MCP
`X.Y.Z` pareia com o novomodelo `X.Y.Z` e com o novomodelo-bridge `X.Y.Z` ou um patch só
dele; uma correção só do MCP, ou um patch só do bridge depois do release do MCP, vira
`X.Y.Z.postN`.

## [Unreleased]

### Added

- O `server_info` traz em `versions.expected_bridge` a versão do bridge que o MCP fixa, que
  pode ser um patch só do bridge; `versions.expected` continua sendo a do novomodelo.

### Changed

- Um patch só do bridge pareia com o novomodelo da mesma versão: o executável, a biblioteca
  e as docs seguem a versão do novomodelo que o bridge fixa, e o bridge, o pin do MCP.

### Fixed

- O `server_info` anuncia um MCP `X.Y.Z.postN` novo, e o comando de reinstalar o MCP nos
  `version_warnings` fixa a versão instalada, com o `.postN`.

## [0.21.0] - 2026-11-17

### Changed

- **BREAKING:** as chaves que o próprio MCP escreve nas respostas passam a ser em inglês.
  O texto para pessoas (mensagens, `diagnostics`, avisos, docstrings) continua em
  português. Não mudam as chaves repassadas das CLIs e do `novomodelo-python`, as do
  `config.json` do caso, nem o `pastas.json` do state dir. Um conceito com dois nomes
  passa a ter um só: `truncated`, `note`, `error`, `origin` e `version` em toda resposta,
  e `next` para o passo seguinte (como no `deck_list`).

  | Onde                                         | Antes                                                                                                                                    | Agora                                                                                                                                             |
  | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
  | toda resposta                                | `avisos_de_versao`                                                                                                                       | `version_warnings`                                                                                                                                |
  | respostas com teto de tamanho                | `cortado_por_tamanho` {`teto_kb`, `linhas_devolvidas`, `linhas_antes_do_corte`}; `truncado` na lista cortada                             | `size_truncation` {`limit_kb`, `rows_returned`, `rows_total`}; `truncated`                                                                        |
  | recusa do guard                              | `pasta_sugerida`                                                                                                                         | `suggested_folder`                                                                                                                                |
  | `include_folders`                            | `incluidas`, `ja_incluidas`, `recusadas` [{`pasta`, `motivo`}], `raizes`, `aviso`                                                        | `included`, `already_included`, `refused` [{`folder`, `reason`}], `roots`, `note`                                                                 |
  | `server_info`                                | `versao_mcp`, `pastas_incluidas`, `bridge.origem`, `erro`                                                                                | `mcp_version`, `included_folders`, `bridge.origin`, `error`                                                                                       |
  | `server_info.versoes` → `versions`           | `executavel`, `biblioteca`, `versao`, `motivo`, `origem`, `esperada`                                                                     | `executable`, `library`, `version`, `reason`, `origin`, `expected`                                                                                |
  | `server_info.versao_nova` → `new_version`    | `mais_recente`, `comando`, `nota`, `notas`, `mudancas`, `aviso_rede`, `verifique_em`                                                     | `latest`, `command`, `note`, `release_notes`, `release_changes`, `network_warning`, `check_at`                                                    |
  | `server_info.docs`                           | `origem`, `caminho`, `versao`                                                                                                            | `origin`, `path`, `version`                                                                                                                       |
  | `install_novomodelo`                         | `executado`, `plano` {`versao`, `destino`, `altera_path`}, `comando_manual`, `versao_instalada`, `caminho`, `configuracao`, `aviso_rede` | `executed`, `plan` {`version`, `destination`, `modifies_path`}, `manual_command`, `installed_version`, `path`, `configuration`, `network_warning` |
  | `case_summary`                               | `contagens`, `itens` {`lista`, `truncado`}                                                                                               | `counts`, `items` {`entries`, `truncated`}                                                                                                        |
  | `case_summary`, tipos                        | `barras`, `linhas`, `hidros`, `termicas`, `contratos`, `bombeamento`, `fontes_nao_controlaveis`, `estagios`                              | `buses`, `lines`, `hydros`, `thermals`, `contracts`, `pumping_stations`, `non_controllable_sources`, `stages`                                     |
  | `case_validate`                              | `warnings_agrupados`, `warnings_grupos_total`; em cada grupo, `mensagem_modelo`, `exemplos`                                              | `warnings_grouped`, `warnings_groups_total`; `message_template`, `examples`                                                                       |
  | `results_*`, recusa da pasta do caso         | `output_sugerido`, `rodadas`, `rodadas_total`                                                                                            | `suggested_output`, `runs`, `runs_total`                                                                                                          |
  | `results_status`, `run_status`               | `treino`, `simulacao`                                                                                                                    | `training`, `simulation`                                                                                                                          |
  | `results_status`, `run_status`               | `escalonamento` {`razao_pre`, `razao_pos`, `estagio`, `faixa`}                                                                           | `scaling` {`pre_ratio`, `post_ratio`, `stage`, `range`}                                                                                           |
  | `results_status`, `run_status`               | `diagnostico_heuristico` {`razao`, `faixa`, `estagio`, `nota`}                                                                           | `heuristic_diagnosis` {`ratio`, `range`, `stage`, `note`}                                                                                         |
  | `results_query`                              | `limite_aplicado`, `proximo_passo`                                                                                                       | `limit_applied`, `next`                                                                                                                           |
  | `deck_describe_parquet`, `deck_edit_parquet` | `proximo_passo`                                                                                                                          | `next`                                                                                                                                            |
  | `results_stochastic`                         | `par` {`linhas`, `truncado`}, `aberturas` {`estagio`, `n_aberturas`, `linhas`, `truncado`}                                               | `par` {`rows`, `truncated`}, `openings` {`stage`, `n_openings`, `rows`, `truncated`}                                                              |
  | `results_policy`                             | `estagios` [{`n_cortes`, `n_ativos`}], `estagios_truncado`, `graph_manifest` {`n_nos`, `n_arestas`}                                      | `stages` [{`n_cuts`, `n_active`}], `stages_truncated`, `graph_manifest` {`n_nodes`, `n_edges`}                                                    |
  | `results_policy` com `stage`                 | `cortes` {`estagio`, `linhas` [{`n_coeficientes`}], `truncado`}                                                                          | `cuts` {`stage`, `rows` [{`n_coefficients`}], `truncated`}                                                                                        |
  | `run_start`                                  | `output_sugerido`                                                                                                                        | `suggested_output`                                                                                                                                |
  | `run_logs`                                   | `saida`                                                                                                                                  | `log`                                                                                                                                             |
  | `schema_get`                                 | `tipo`                                                                                                                                   | `type`                                                                                                                                            |
  | `docs_list`                                  | `itens` [{`pagina`, `titulo`, `descricao`}]                                                                                              | `items` [{`page`, `title`, `description`}]                                                                                                        |
  | `docs_read`                                  | `secao`, `titulo`; sem `page`, `aviso`; seção inexistente, `secoes` [{`titulo`, `ancora`}]                                               | `section`, `title`; `note`; `sections` [{`title`, `anchor`}]                                                                                      |
  | `docs_search`                                | `consulta_usada`, `termos_do_glossario`, `resultados` [{`pagina`, `secao`, `titulo`, `trecho`}]                                          | `query_used`, `glossary_terms`, `results` [{`page`, `section`, `title`, `snippet`}]                                                               |
- **BREAKING:** as tools `incluir_pastas` e `instalar_novomodelo` passam a se chamar
  `include_folders` e `install_novomodelo`, e os parâmetros em português passam ao
  inglês. Uma lista de liberação do cliente feita à mão com os nomes antigos precisa ser
  refeita. O resource `novomodelo://schema/{tipo}` passa a `novomodelo://schema/{type}`
  (a URI de cada schema não muda). As instruções do servidor, o prompt `metodologia` e a
  linha que o `configurar` grava nas instruções do cliente pedem a citação como
  `page#section`. O `section` do `docs_list`, que é um prefixo do caminho da página,
  passa a `prefix`: no `docs_read` e no `docs_search`, `section` é a âncora de uma seção.

  | Tool                                         | Antes                                    | Agora                    |
  | -------------------------------------------- | ---------------------------------------- | ------------------------ |
  | `incluir_pastas` → `include_folders`         | `pastas`                                 | `folders`                |
  | `instalar_novomodelo` → `install_novomodelo` | `confirmar`, `pasta`                     | `confirm`, `install_dir` |
  | `bridge_convert_decomp`                      | `importar_fcf`                           | `import_fcf`             |
  | `results_stochastic`                         | `aberturas_do_estagio`                   | `openings_stage`         |
  | `schema_get`                                 | `tipo`                                   | `type`                   |
  | `docs_search`                                | `consulta`                               | `query`                  |
  | `docs_read`                                  | `secao`                                  | `section`                |
  | `docs_list`                                  | `section` (prefixo do caminho da página) | `prefix`                 |
- O MCP pareia com o novomodelo 0.21.0 e o novomodelo-bridge 0.21.0. As docs embutidas
  são as da 0.21.0, e as páginas `changelog/novomodelo` e `changelog/novomodelo-bridge`
  trazem a seção da 0.21.0.
- **Para quem atualiza da 0.20:** `uv tool upgrade novomodelo-mcp`, fechar e abrir o
  cliente e atualizar o executável `novomodelo` para a 0.21: peça ao agente "instale o
  executável do novomodelo", como o aviso de versão indica. O agente lê os nomes novos do
  servidor a cada conversa, e a lista de tools de leitura que o `configurar` libera é a
  mesma. Fora isso, só precisa agir quem liberou à mão
  `incluir_pastas` ou `instalar_novomodelo` no cliente (troque pelos nomes novos) ou tem
  script, integração ou instruções próprias com os nomes antigos (veja as tabelas acima).
  A linha que o `configurar --instrucoes` gravou no `~/.claude/CLAUDE.md` continua
  funcionando; para a citação como `page#section`, apague a linha marcada com
  `<!-- novomodelo-mcp -->` e rode o `configurar --instrucoes` de novo.
- As versões mínimas das dependências passam a ser as que a CI testa: mcp 1.30.0,
  polars 2.1.0, jsonschema 4.26.0, duckdb 2.0.0 e truststore 0.10.5. As mínimas
  anteriores não instalavam um servidor funcional (o mcp antes da 1.11 nem importa com o
  pydantic atual).
- O `docs_read` aceita a página como as docs a citam: o link de dentro de uma página
  (`/en/running/configuration/#training`, com a âncora virando a seção), o endereço do
  site e a página em pt-BR. Ele lê a página em inglês, que é a fonte, e diz em `note` qual
  página leu e como citá-la.
- As respostas das tools do bridge cabem no teto `NOVOMODELO_MCP_MAX_RESPONSE_KB`: as tabelas
  dos diagnósticos perdem as últimas linhas, a maior tabela primeiro, e todo diagnóstico
  continua na resposta. Cada tabela cortada traz `truncated` e `rows_total`, e a resposta
  traz `size_truncation`. Só quando cortar as tabelas não basta a lista de diagnósticos
  é cortada.
- O `server_info` mostra também as entradas de `Removed` e as dos temas `####` das notas
  do novomodelo e do bridge, e põe antes de todas as BREAKING de qualquer seção. BREAKING
  é o item que começa com `BREAKING:`; a palavra no meio do texto não conta mais.
- As notas de cada release do MCP no GitHub trazem a seção da versão no `CHANGELOG.md`.
- As descrições do `run_apply` e do `deck_edit_json` dizem que forward passes, limite de
  iterações e cenários da simulação se mudam pelo `run_apply`, depois do `run_plan`. O
  exemplo do `deck_edit_json` era o limite de iterações, e o agente às vezes editava o
  `config.json` à mão em vez de usar o `run_apply`.

### Fixed

- Toda resposta de erro traz `exit_code` e `diagnostics`. Alguns erros do `deck_edit_json`,
  do `deck_edit_parquet`, do `schema_get` e do `docs_read` vinham sem `exit_code`, e a
  validação reprovada do `case_validate` vinha sem `diagnostics`.
- Quando os runs de referência não tinham medição do treino (por exemplo, uma entrada do
  registro de calibração editada à mão), o `run_plan` respondia com um erro `TypeError` e
  o `run_start` recusava rodar. O plano agora sai `indeterminado`, como quando não há
  referência, e o `run_start` roda.

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
