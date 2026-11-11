# Bateria E2E do novomodelo-mcp

Testes de integração do servidor MCP com as CLIs reais (`novomodelo-bridge`, `novomodelo`) e dados reais. A bateria mede se as tools respondem como esperado, se um agente de IA as escolhe e usa bem, e como o servidor se comporta sob carga concorrente.

Autores originais da bateria: Raquel Pereira Grillo e João Weydt.

## Estrutura

```
e2e/
├── pyproject.toml          # Projeto novomodelo-mcp-e2e: membro do workspace do uv, não publicado
├── novomodelo_mcp_e2e/
│   ├── __main__.py         # CLI da bateria: verificar, preparar, rodar, go-no-go, marcar-lancamento
│   ├── config.py           # Configuração pelo ambiente e verificação antes da rodada
│   ├── rodada.py           # Rodada: determinística, conjuntos com agente, retomada, trava e varredura de segredos
│   ├── executor/           # Imagens (Containerfile), container endurecido, leitores do stream e máscara de segredos
│   ├── conjuntos/          # Conjuntos com agente: tools (casos de queries/cases.yaml) e usuário (cenários e juiz)
│   ├── resultado/          # Manifesto, registro e decisão com JSON Schema versionado; JUnit
│   ├── go_no_go/           # Critério de go/no-go, relatório e lançamentos marcados
│   ├── queries/            # Casos do conjunto tools e validador das tools chamadas (queries/README.md)
│   ├── launcher/           # Servidor local (FastAPI, só em 127.0.0.1) que dispara as rodadas e a carga pelo painel (launcher/README.md)
│   └── load/               # Teste de carga: N clientes, um servidor MCP por cliente (load/README.md)
└── frontend/               # Painel React/Vite com histórico, comparação e carga (frontend/README.md)
```

A bateria é um projeto à parte no workspace do uv (`e2e/pyproject.toml`), com as dependências dela e a configuração de pytest dela. Fica fora do sdist e do wheel do novomodelo-mcp, e o `pytest` padrão do repositório só coleta `tests/`.

## Pré-requisitos

- Python e as dependências da bateria: `uv sync --package novomodelo-mcp-e2e`
- `novomodelo-bridge` e `novomodelo` no `PATH`, para a bateria determinística
- `podman` e `gitleaks` no `PATH`, para as rodadas com agente e a varredura de segredos
- Para o painel: Node.js e `npm --prefix e2e/frontend ci`
- Os agentes (Claude Code e Kiro) rodam só no container do executor, com as versões fixadas na imagem; o token do Claude entra por arquivo `600` e secret do podman, e o login do Kiro, pelo volume dele (ver a tabela abaixo)
- Opcional, para medir CPU e memória no teste de carga: `psutil`, fora das dependências da bateria; sem ele a carga roda e o relatório diz que a medida não está disponível

Os decks e demais dados dos casos ficam numa pasta `fixtures` dentro de `novomodelo_mcp_e2e/`, ao lado do código da bateria, ignorada pelo git.

## Como rodar

A bateria inteira de testes automatizados (as suítes `*_unit.py` e a de integração do `load/`):

```bash
uv sync --package novomodelo-mcp-e2e
uv run --package novomodelo-mcp-e2e pytest e2e -q
```

Cada parte também roda sozinha:

```bash
uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e.queries.run_queries       # recusa fora do executor em container
uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e.load.run --concurrency 4 --duration 30
```

## Rodada com agentes e veredito

O fluxo roda no executor em container (podman), pela CLI `python -m novomodelo_mcp_e2e`:

```bash
uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e verificar
uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e preparar --mcp sem caminho/da/wheel.whl
uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e rodar --mcp caminho/da/wheel.whl --rodada ID
uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e go-no-go ID --alvo CONFIG [--baseline RODADA] [--baseline-config CONFIG]
uv run --package novomodelo-mcp-e2e python -m novomodelo_mcp_e2e marcar-lancamento ID VERSAO --config CONFIG
```

- `verificar` confere motor, pastas, token e volume do Kiro; `preparar` constrói as imagens e cria o secret do token; `rodar` grava o manifesto e um registro por execução e é retomável pelo `--rodada`.
- `go-no-go` grava `relatorio-go-no-go.md`, `junit.xml` e `decisao-go-no-go.json` na pasta da rodada, depois de o gitleaks varrê-la com o `.gitleaks.toml` do repositório; achado ou varredura que não roda grava `BLOQUEADO-SEGREDO.txt` e nada mais. Só uma rodada completa decide: execução do plano do manifesto sem registro (no alvo ou na base) ou último `fim` do `rodada.jsonl` com código diferente de 0 dão inconclusivo, com a lista do que falta (um no-go já observado continua no-go). Rodada com o `rodar` em andamento é recusada. A base de comparação é, nesta ordem: `--baseline-config` (na mesma rodada, ou na de `--baseline` quando vêm juntas), `--baseline`, o último lançamento marcado, ou nenhuma (só a determinística bloqueia). O relatório lista, por configuração, a versão, o SHA-256 e a origem do wheel, e as versões de cada imagem.
- `marcar-lancamento` torna uma configuração da rodada a base do próximo `go-no-go`; só por decisão de quem libera a versão, e só com a configuração completa na rodada.

A decisão do `go-no-go` é consultiva: informa quem libera a versão e não bloqueia o release (`CONTRIBUTING.md`, "Release").

Variáveis de ambiente da `Config` (todas opcionais):

| Variável | O que faz | Default |
|---|---|---|
| `NOVOMODELO_BATERIA_MOTOR` | Motor de container; só o `podman` é aceito | `podman` se estiver no `PATH`, senão `docker`, que o `verificar` recusa |
| `NOVOMODELO_BATERIA_RESULTADOS` | Pasta das rodadas e do `lancamentos.json` | pasta de dados do usuário, `novomodelo-mcp-bateria/resultados` |
| `NOVOMODELO_BATERIA_CASOS` | Pasta com um subdiretório por caso grande | não definida: esses casos ficam pulados |
| `NOVOMODELO_BATERIA_CENARIOS_EXTRA` | Pasta de cenários extras, fora do repositório | não definida |
| `NOVOMODELO_BATERIA_TOKEN_CLAUDE` | Arquivo (permissão `600`, fora do repositório) com o token do Claude | `token-claude` na pasta de configuração do usuário |
| `NOVOMODELO_BATERIA_VOLUME_KIRO` | Volume do podman com o login do Kiro | `novomodelo-bateria-kiro` |
| `NOVOMODELO_BATERIA_MEMORIA` | Limite de memória de cada container | `6g` |

Códigos de saída do `rodar`: 0 rodada completa; 1 problema do ambiente apontado pela verificação (motor, pastas, token, volume), determinística com falha, imagem não pronta ou execução sem registro; 2 argumentos inválidos ou retomada recusada; 3 segredo na pasta da rodada; 4 limite de uso do agente ou do juiz; 5 orçamento estourado; 130 Ctrl-C.

Códigos de saída do `go-no-go` (outro subcomando, outra tabela): 0 go; 1 no-go; 2 inconclusivo, inclusive rodada incompleta; 3 segredo bloqueado na rodada ou varredura que não rodou; 64 recusa de uso (argumentos inválidos, rodada em andamento, rodada, alvo ou configuração inexistente, manifesto ilegível, `--baseline` igual à própria rodada sem `--baseline-config`, lançamento marcado cuja rodada ou configuração não existe mais).

Base de um lançamento cuja rodada está bloqueada por segredo, ausente ou sem a configuração sai com 64 e a mensagem "base indisponível". Erros de uso do `argparse` nesses dois subcomandos também saem com 64.

Códigos de saída do `marcar-lancamento`: 0 marcado; 3 rodada bloqueada por segredo; 64 recusa de uso (argumentos inválidos, rodada ou configuração inexistente, rodada em andamento ou incompleta, manifesto ou `lancamentos.json` ilegível).

## Configuração

Tudo vem de variável de ambiente (a tabela da `Config` acima) ou de argumento. O timeout de cada caso vem do `timeout_s` de `queries/cases.yaml` (por caso ou grupo).

Nunca grave credenciais em arquivo do repositório. Lê-las de um arquivo fora do repositório com permissão `600` mantém o valor fora do código e dos logs.

## Riscos residuais aceitos

Um hard link dentro de um caso que aponte para um arquivo fora dele entra na cópia do caso, e há uma janela estreita entre conferir um caminho e usá-lo; os dois exigem escrita na pasta de casos, que é de quem roda a bateria.

## Painel

```bash
npm --prefix e2e/frontend ci
npm --prefix e2e/frontend run build
```

Lint, testes e servidor de desenvolvimento do painel estão em `frontend/README.md`.
