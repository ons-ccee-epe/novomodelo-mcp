# Dashboard de Testes E2E — novomodelo-mcp (frontend)

Painel que mostra as rodadas da bateria e dispara novas. Ele lê tudo do launcher de dev
(FastAPI) e não gera HTML a cada execução.

## Stack

React 19 + TypeScript + Vite 6, HashRouter, Radix UI Themes, Recharts e SVG
próprio para os gráficos, react-markdown (com remark-gfm) para a resposta do agente, Vitest
para testes. As dependências estão fixadas em versões exatas.

## Como rodar

```bash
cd e2e/frontend
npm ci               # versões do package-lock.json; Node em engines.node
npm run dev:launcher # sobe o launcher (porta 5175) e o painel (http://127.0.0.1:5174)
```

`npm run dev` sobe só o painel; ele precisa do launcher no ar. `npm run dev:tests` roda
uma rodada (`python -m novomodelo_mcp_e2e rodar`, argumentos depois de `--`) e depois sobe os dois.

Build estático:

```bash
npm run build        # gera dist/
npm run preview
```

O build não leva dados: o painel os lê do launcher em tempo de execução.

## De onde vêm os dados

O painel não lê arquivo do disco. Tudo passa por `src/data/rodada.ts`, que fala com o
launcher:

| Rota                      | Conteúdo                                                            |
| ------------------------- | ------------------------------------------------------------------- |
| `GET /api/rodadas`        | resumo de cada rodada gravada                                       |
| `GET /api/rodadas/{id}`   | manifesto, registros e a decisão do go-no-go (quando já rodou)      |
| `POST /api/rodadas`       | dispara uma rodada com as opções da lista branca do launcher        |
| `GET /api/command-preview`| o comando equivalente de um disparo                                 |
| `GET /data/results/load/` | as cargas gravadas (Testes de Carga e o Histórico de carga)         |

Em dev, o Vite repassa `/api` e `/data` ao launcher (`VITE_LAUNCHER_URL`). Os tipos de
`rodada.ts` são conferidos por teste contra `e2e/novomodelo_mcp_e2e/resultado/schemas/` (manifesto,
registro e decisão); um `schema_versao` desconhecido é recusado.

## Áreas

A barra do topo (`navigation/AppNav.tsx`) liga três áreas (HashRouter) e traz o botão de
modo noturno (a escolha fica no `localStorage` do navegador) e a engrenagem com a última
rodada, as configurações dela, o estado do launcher e o transporte. A raiz e qualquer rota
desconhecida levam a `/#/funcionais`.

- **Testes Funcionais** (`/#/funcionais`): monta e dispara uma rodada (wheels, conjuntos,
  agentes, filtro, repetições e os limites da lista branca), com o comando equivalente.
  Precisa do launcher; ele recusa com 409 enquanto outro run está ativo.
- **Testes de Carga** (`/#/carga`): dispara o teste de carga do servidor MCP, com o
  progresso ao vivo e **Parar**. Detalhes em [`../load/README.md`](../load/README.md).
- **Histórico**: a chave **Rodadas | Carga** no topo da lista escolhe o que aparece.
  - **Rodadas** (`/#/historico` e `/#/historico/:rodadaId`): no topo, o veredito do
    go-no-go (com os bloqueios e a evidência) e as configurações (versão, SHA-256 e
    origem de cada wheel, versões das imagens). Depois, o filtro por conjunto:
    determinística, tools e usuário. O usuário traz as configurações lado a lado por
    agente, o detalhe por cenário e a nota com a justificativa do juiz. O tools traz os
    gráficos, as perguntas, a variação e a evolução entre rodadas, por configuração e
    agente, e o **Baixar resumo**. A comparação com outra rodada lista as regressões.
  - **Carga** (`/#/historico/carga` e `/#/historico/carga/:loadId`): as cargas gravadas,
    a comparação com a anterior e os gráficos.

O registro do conjunto tools não guarda o texto da pergunta, a tool esperada, os
argumentos das chamadas nem a resposta do agente; a tela diz isso e usa o id do caso e o
grupo da primeira tool chamada.

## Estrutura

Layout:

```
src/
  main.tsx                       # entrypoint (HashRouter + Radix Theme)
  data/rodada.ts                 # única fonte dos dados das rodadas: tipos, adaptadores, seletores
  navigation/                    # rotas e barra de navegação
  shared/constants/Routes.ts     # path de cada tela
  shared/constants/status.ts     # ícones e rótulos de status
  shared/components/TestDetail.tsx # detalhe de uma pergunta do conjunto tools
  shared/types.ts                # lote do conjunto tools e contrato das cargas
  shared/toolGroups.ts           # mapa tool->grupo
  shared/conjunto.ts             # rótulos de conjunto
  shared/comparison.ts           # variação entre dois lotes
  shared/charts/                 # ChartCard e SvgLegend, base dos gráficos com download
  shared/exportPng.ts            # SVG -> canvas -> PNG
  theme/                         # tokens de tema claro e escuro e o modo noturno
  services/launcherApi.ts        # base das rotas, header dos POSTs, saúde do launcher
  services/api/useRodadas.ts     # rodadas, uma rodada e várias para a evolução
  services/loadApi.ts            # cargas: leitura e controle pelo launcher
  services/api/useLoad*.ts       # cargas gravadas, disparo, polling e parada
  features/Functional/           # disparo de uma rodada
  features/History/
    index.tsx                    # rodadas ou cargas, cada uma com lista e dashboard
    charts/                      # os gráficos do conjunto tools
    components/                  # RodadaDashboard, GoNoGo, Configuracoes, AvaliacaoAmpla, ToolsView, ...
  features/Load/                 # disparo e dashboard da carga
```

## Configuração

Host, porta e URL do launcher vêm de `VITE_DEV_HOST`, `VITE_DEV_PORT` e
`VITE_LAUNCHER_URL`; sem elas, valem os defaults do `vite.config.ts`.

## Qualidade

```bash
npm run lint         # ESLint (typescript-eslint + react-hooks)
npm test             # Vitest
npm run build        # tsc -b + vite build
```
