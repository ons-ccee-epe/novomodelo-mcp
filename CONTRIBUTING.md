# Contribuir com o novomodelo-mcp

Esta página põe um checkout para rodar, explica como os testes e as checagens estão
organizados, lista as convenções que a CI confere e descreve o pareamento com o
novomodelo e o release. O uso do produto está no [README](README.md).

## Ambiente de desenvolvimento

```bash
git clone https://github.com/ons-ccee-epe/novomodelo-mcp.git
cd novomodelo-mcp
uv sync --system-certs     # --system-certs: redes com proxy que reassina certificados
uv run novomodelo-mcp      # sobe o servidor no transporte stdio
```

O `uv.lock` é versionado, então o `uv sync` reproduz o ambiente da CI.

> **Rede corporativa:** sem `--system-certs` (ou `UV_SYSTEM_CERTS=1`), o `uv` pode
> falhar no PyPI com `UnknownIssuer` por causa do proxy que reassina certificados.

> **Pasta sincronizada (iCloud, OneDrive):** não desenvolva nem instale dentro dela. O
> iCloud marca os arquivos `.pth` do `.venv` como ocultos, e o Python ignora `.pth`
> ocultos: o `import novomodelo_mcp` falha, e parece faltar `PYTHONPATH`. Se o checkout
> precisa ficar ali, ponha o ambiente fora:
> `UV_PROJECT_ENVIRONMENT=~/.venvs/novomodelo-mcp uv sync` (e o mesmo valor no `uv run`).

O servidor fala **stdio**: não abre porta e é iniciado pelo cliente MCP como
subprocesso. A rede só é usada pelas tools listadas em `NETWORK_TOOLS`
(`src/novomodelo_mcp/tools/annotations.py`), pelo `src/novomodelo_mcp/adapters/versions.py`.

O hook de pre-commit roda antes de cada commit as mesmas checagens de lint e os gates da
CI, inclusive o de termos proibidos, e o gitleaks nas mudanças preparadas quando ele está
instalado (a CI varre o histórico inteiro de qualquer jeito):

```bash
ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
```

## Rodar as checagens

```bash
uv run pytest -q                                      # suíte offline, com binários falsos
uv run ruff check . && uv run ruff format --check .   # lint e formatação, árvore inteira
python3 scripts/ci/check_no_plan_leaks.py             # sem vocabulário de plano no que é publicado
python3 scripts/ci/check_comment_refs.py              # sem referência que apodrece na prosa do código
python3 scripts/ci/check_doc_paths.py                 # todo caminho citado nas docs existe
```

A CI (`.github/workflows/ci.yml`) roda o ruff e os três gates uma vez, a suíte em cada
sistema, arquitetura e versão do Python que o projeto suporta, os testes com os
executáveis reais e a conferência das docs embutidas. `scripts/ci/check_comment_bloat.py`
e `scripts/ci/quality_report.py` são relatórios: nunca falham.

### Níveis de teste

- **Suíte offline (padrão).** Todo `tests/test_*.py`, com os binários falsos
  (`tests/fake_novomodelo.py`, `tests/fake_novomodelo_bridge.py`) e sem rede.
- **Opcionais.** Os testes que precisam dos executáveis reais ou da rede são marcados
  (`executaveis_reais`, `rede`) e pulados por padrão; rodam com as opções:

```bash
uv run pytest --executaveis-reais              # novomodelo e novomodelo-bridge instalados
uv run pytest --executaveis-reais --com-rede   # + o que acessa os domínios oficiais
```

**Bateria de ponta a ponta** contra os programas reais (`tests/test_executaveis_reais.py`):
sobe o servidor como um cliente MCP, confere as anotações que ele anuncia e chama todas as
tools num workspace temporário. As tools do bridge usam os decks mínimos públicos do
novomodelo-bridge (os decks de teste de um clone dele, na tag da versão); sem
`--bridge-repo`, elas ficam puladas:

```bash
uv run pytest -rs tests/test_executaveis_reais.py --executaveis-reais \
    --bridge-repo /caminho/para/novomodelo-bridge
uv run pytest -rs tests/test_executaveis_reais.py --executaveis-reais --claude-code   # + aprovação no Claude Code
```

As outras opções: `--mcp-instalado [CAMINHO]` (o pacote instalado em vez do código-fonte),
`--instalar-executavel` (instala o executável pela tool antes da bateria; use com `--com-rede`),
`--newave-src` e `--decomp-src` (casos próprios). `tests/conftest.py` é o dono delas.

`tests/try_tools.py` é um utilitário manual, fora da CI.

**Bateria e2e com agentes** (`e2e/`): rodadas com o Claude Code e o Kiro num executor em
container, juiz, go/no-go, teste de carga e o painel. É um projeto à parte no workspace do
uv (`e2e/pyproject.toml`, `novomodelo-mcp-e2e`), fora do sdist e do wheel, e o
`uv run pytest` da raiz não a coleta. A CI roda a suíte dela num job próprio, além do lint,
dos testes e do build do painel:

```bash
uv sync --package novomodelo-mcp-e2e
uv run --package novomodelo-mcp-e2e pytest e2e -q
```

Pré-requisitos, rodadas, go/no-go, carga e painel estão em `e2e/README.md`.

## Convenções que a CI confere

As regras em `.claude/rules/` são escritas para um agente agir sobre elas e valem também
para quem programa:

- **Fachada fina.** Uma tool envolve um subcomando de CLI (com `--json`) ou a
  `novomodelo-python` e repassa o resultado; comportamento novo vai para o novomodelo ou
  o novomodelo-bridge. Envelope de erro em vez de exceção, guarda de pasta fail-closed,
  rede só pelos domínios oficiais e escrita forçada só com `NOVOMODELO_MCP_ALLOW_FORCE=1`
  (`.claude/rules/mcp-facade.md`).
- **Paridade NEWAVE/DECOMP.** Uma tool de uma trilha de conversão sai com a da outra na
  mesma mudança, ou a assimetria é registrada.
- **Superfície das CLIs.** `tests/surface.toml` classifica cada subcomando e opção do
  novomodelo e do novomodelo-bridge; `tests/test_surface_parity.py` falha com uma opção
  sem classificação.
- **Comentários desligados por padrão** (`.claude/rules/comments.md`).
- **Docs não congelam contagem nem versão à mão**, não citam caminho que não existe e não
  usam vocabulário de plano (`.claude/rules/doc-integrity.md`).
- **Commits** em [Conventional Commits](https://www.conventionalcommits.org/): `feat`,
  `fix`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`, `chore`.
- `.kiro/steering/` é gerado do `CLAUDE.md` e de `.claude/rules/` por
  `scripts/gen/sync-kiro-steering.py`; não edite à mão.

## Atualizar as docs embutidas

```bash
uv run python scripts/sync_bundled.py --source /caminho/para/clone/do/novomodelo-docs \
  --changelog novomodelo=/caminho/para/clone/do/novomodelo \
  --changelog novomodelo-bridge=/caminho/para/clone/do/novomodelo-bridge
# o mesmo comando com --check só confere
```

Os clones ficam na tag da versão. Os changelogs do novomodelo e do bridge viram as
páginas `changelog/novomodelo` e `changelog/novomodelo-bridge`, com uma seção por versão
a partir da 0.18.0, que o agente lê com `docs_read(page, "<versão>")`. O commit de cada
clone fica no `manifest.json`.

O script grava as páginas já resolvidas (os trechos `_impl` entram no lugar dos
componentes, e a marcação MDX sai), os schemas, o índice de busca
(`_bundled/docs_index.sqlite`) e o manifesto (versão do `versions.json` das docs e commit
do clone). Com `--check`, não grava e sai com erro se o embutido divergir da fonte; a CI
roda essa checagem no commit gravado no manifesto.

Para testar mudanças nas docs antes de um release, `NOVOMODELO_MCP_DOCS_DIR` aponta para
a pasta de páginas de um clone do novomodelo-docs. É uma opção de desenvolvimento: com
ela, toda resposta traz um aviso em `version_warnings`.

## Organização do código

- `src/novomodelo_mcp/server.py` sobe o FastMCP e registra as tools; `config.py` lê os
  `Settings` do ambiente (prefixo `NOVOMODELO_MCP_`); `names.py` declara os nomes dos
  programas externos.
- `src/novomodelo_mcp/adapters/` é a única camada que toca processo, arquivo ou binding:
  as CLIs, a guarda de pasta, o envelope de erro (fonte única), a rede, os runs
  assíncronos e o estado.
- `src/novomodelo_mcp/tools/` é o que o agente enxerga: registra as tools, as anotações
  MCP e molda a saída.
- `src/novomodelo_mcp/_bundled/` é a cópia embutida das docs e dos schemas.

A docstring de cada módulo diz o que ele faz.

## Renomear o produto

O rename do produto é feito pela
ferramenta do novomodelo (o `rebrand.py` do repositório dele), guiada por
`scripts/rebrand/map.toml`:

```bash
R=/caminho/para/novomodelo/scripts/rebrand/rebrand.py
M=scripts/rebrand/map.toml
uv run --no-sync python $R paths  --root . --map $M   # move caminhos (git mv); commitar sozinho
uv run --no-sync python $R tokens --root . --map $M   # reescreve conteúdo
uv run --no-sync python $R check  --root . --map $M   # 0 ocorrências = pronto
```

Para o próximo nome, crie um mapa com `from = "novomodelo"`. As exceções atuais estão
comentadas no próprio mapa. A CI roda o `check` em todo push e PR (job `rename-guard`),
com a ferramenta do novomodelo fixada numa tag.

## Parear com uma versão do novomodelo

O MCP `X.Y.Z` pareia com o novomodelo `X.Y.Z`. O MCP fixa `novomodelo-bridge==X.Y.Z`, o
bridge fixa `novomodelo-python==X.Y.Z`, e `expected_version()`
(`src/novomodelo_mcp/adapters/versions.py`) lê a versão esperada desse pin.

O pareamento é um commit só, `build: pair with novomodelo X.Y.Z`, feito depois que o
bridge `X.Y.Z` está no PyPI e as docs têm a tag `vX.Y.Z`:

1. `version` e o pin do bridge no `pyproject.toml`, e o lock:
   `uv lock --upgrade-package novomodelo-bridge --upgrade-package novomodelo-python`.
   `tests/test_package_metadata.py` falha se a versão do MCP e o pin divergirem.
2. As docs embutidas e os changelogs nas tags `vX.Y.Z` (seção acima).
3. O `ref` do job `rename-guard` em `.github/workflows/ci.yml` para `vX.Y.Z`.
4. Cada opção nova das CLIs classificada em `tests/surface.toml`; confira com
   `uv run pytest tests/test_surface_parity.py --executaveis-reais` contra o novomodelo e
   o bridge `X.Y.Z` instalados.
5. As entradas de `Unreleased` do `CHANGELOG.md` sob a versão nova.

Uma correção só do MCP vira `X.Y.Z.postN`.

## Release

Quem mantém o repositório cria a tag `vX.Y.Z`, igual à `version` do `pyproject.toml`, e
faz o push. `.github/workflows/release.yml`:

1. confere a tag contra a `version` e as docs embutidas contra os commits gravados no
   manifesto, e roda os testes;
2. gera o wheel, o sdist e o `SHA256SUMS` dos dois, e confere que toda dependência tem
   wheel em cada alvo e versão do Python suportados (`scripts/conferir_wheels.sh`): quem
   instala resolve na hora, sem o `uv.lock`, e não deve precisar compilar nada;
3. instala o wheel com `uv tool install` num diretório vazio, em cada sistema,
   arquitetura e versão do Python suportados, e confere pelo stdio a versão anunciada, as
   tools e o `server_info` (`scripts/conferir_instalacao.py`);
4. publica no PyPI por trusted publishing, só no repositório público e pelo environment
   `pypi`, e anexa os arquivos ao release do GitHub.

Para ensaiar sem publicar, faça push numa branch `ensaio/<nome>` (ou use "Run workflow"
na aba Actions): os arquivos ficam como artefato da execução.

A decisão de go/no-go da bateria e2e (`e2e/README.md`) é consultiva: informa quem cria a
tag, mas não bloqueia o release, e o `release.yml` não roda a bateria.

Se a organização não permitir `contents: write` ao `GITHUB_TOKEN`, o job do release do
GitHub falha e o resto continua valendo. Nesse caso, baixe o artefato da execução e
anexe à mão: `gh release create vX.Y.Z novomodelo_mcp-*.whl novomodelo_mcp-*.tar.gz
SHA256SUMS --title "novomodelo-mcp X.Y.Z"`.
