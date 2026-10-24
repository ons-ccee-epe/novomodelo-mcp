# Dashboard de Testes E2E — <repositório anterior> (frontend)

Frontend único que **consome os resultados dos testes** em vez de gerar HTML a
cada execução. Os runners de teste gravam JSON; este frontend lê esses JSON e se
atualiza a cada refresh.

## Stack

React 19 + TypeScript + Vite 6, HashRouter, Radix UI Themes, Recharts para os
gráficos de tendência, Vitest para testes. Sem backend — hospedagem estática.

## Como rodar

```bash
cd tests/e2e/frontend
npm install          # primeira vez
npm run dev          # http://127.0.0.1:5174
```

Rode os testes E2E normalmente (gera/atualiza os JSON em `../results` e
`../metrics`) e dê **refresh** no dashboard — ou clique em **↻ Atualizar**.

Build estático (para publicar):

```bash
npm run build        # gera dist/ e copia os JSON para dist/data/
npm run preview
```

## De onde vêm os dados

O frontend busca tudo sob `/data`:

| Rota                         | Arquivo real                         | Conteúdo                       |
| ---------------------------- | ------------------------------------ | ------------------------------ |
| `/data/results/index.json`   | `tests/e2e/results/index.json`       | lista de baterias              |
| `/data/results/<id>.json`    | `tests/e2e/results/<id>.json`        | uma bateria completa           |
| `/data/results/baseline.json`| `tests/e2e/results/baseline.json`    | ponteiro da baseline           |
| `/data/metrics/history.jsonl`| `tests/e2e/metrics/history.jsonl`    | histórico (tendências)         |
| `/data/results/load/index.json` | `tests/e2e/results/load/index.json` | lista de cargas (aba Carga)  |
| `/data/results/load/<id>.json`  | `tests/e2e/results/load/<id>.json`  | uma carga completa           |

- **Em dev**: o plugin `resultsDataPlugin` (em `vite.config.ts`) serve `/data`
  lendo direto do disco — nenhuma cópia, sempre o estado atual.
- **No build**: `scripts/copy-data.mjs` (hook `postbuild`) copia os JSON para
  `dist/data/`, inclusive `results/load/`.

O contrato de tipos (`src/shared/types.ts`) espelha os dataclasses de
`tests/e2e/queries/models.py` e o formato de `tests/e2e/queries/store.py`.

## Áreas

A navegação no topo (`navigation/AppNav.tsx`) liga duas áreas (HashRouter):

- **Dashboard** (`/#/`): baterias de teste por agente de IA.
- **Carga** (`/#/carga`): teste de carga do servidor MCP. Formulário (tools,
  concorrência, duração ou iterações, timeout), progresso ao vivo com **Parar**,
  e, para a carga selecionada, cards (vazão, taxa de erro, p50/p95/p99), gráfico de
  latência e vazão no tempo, tabela por tool, detalhes (subida dos servidores,
  recursos, erros, chamadas fora do mix) e a comparação com a carga anterior (ou outra
  à escolha). Com o launcher offline mostra só as cargas gravadas, em leitura.
  Detalhes do teste em [`../load/README.md`](../load/README.md).

## O que mudou nos runners

A geração de HTML foi aposentada; os runners seguem gravando os JSON:

- `tests/e2e/queries/run_queries.py --report` → imprime como abrir o frontend.
- `tests/e2e/eval/run.py` → grava `reports/latest.json`, sem `latest.html`.
- `tests/eval/pytest_bridge.py` → grava `reports/latest.json`, sem `latest.html`.

Os geradores HTML antigos (`*/dashboard.py`, em JS vanilla, fora do padrão de
frontend) foram removidos; este frontend é o único dashboard.

## Estrutura

Segue o layout do padrão de frontend:

```
src/
  main.tsx                       # entrypoint (HashRouter + Radix Theme)
  navigation/index.tsx           # rotas
  shared/constants/Routes.ts     # path de cada tela
  shared/constants/status.ts     # ícones de status
  shared/types.ts                # contrato de dados (espelha o store.py)
  shared/toolGroups.ts           # mapa tool->grupo (espelha store.TOOL_GROUPS)
  theme/styles.css               # tokens de tema (sem cor literal nos componentes)
  services/resultsApi.ts         # fetch dos JSON + parse do JSONL
  services/launcherApi.ts        # controle do launcher (polling cancelável)
  services/api/useResults.ts     # carga de index/bateria/comparação/histórico
  services/api/useLauncher.ts    # provedores, casos e disparo de runs
  services/loadApi.ts            # cargas: leitura de results/load e controle pelo launcher
  services/api/useLoadResults.ts # index, carga selecionada e comparação
  services/api/useLoadLauncher.ts# tools/limites, disparo, polling e parada da carga
  navigation/AppNav.tsx          # barra de navegação e layout das rotas
  features/Dashboard/
    index.tsx                    # tela do dashboard
    alertRules.ts                # regras do banner de saúde (limiares nomeados)
    components/                  # SummaryCards, TrendCharts, TestTable, ...
      launcher/                  # partes do TestLauncher
      table/                     # partes do TestTable
  features/Load/
    index.tsx                    # tela da carga
    compare.ts                   # deltas entre duas cargas (melhor/pior por métrica)
    components/                  # LoadForm, LoadProgress, LoadCharts, LoadToolTable, ...
```

## Configuração

Host, porta e URL do launcher vêm de `VITE_DEV_HOST`, `VITE_DEV_PORT` e
`VITE_LAUNCHER_URL` (ver `.env.template`); sem `.env`, valem os defaults do
`vite.config.ts`.

## Qualidade

```bash
npm run lint         # ESLint (typescript-eslint + react-hooks)
npm test             # Vitest
npm run build        # tsc -b + vite build
```
