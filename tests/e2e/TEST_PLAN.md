# Plano de Testes E2E — <repositório anterior>

Este documento detalha todos os casos de teste para as tools MCP do COBRE, organizados por:
1. **Testes de Integração (I-xxx)** — Verifica se a tool está sendo chamada corretamente pelo MCP
2. **Testes Funcionais (F-xxx)** — Verifica se a tool faz o que deveria fazer
3. **Testes de Erro (E-xxx)** — Verifica se a tool detecta e reporta erros corretamente

---

## Fixtures Disponíveis

| ID | Tipo | Caminho | Descrição |
|----|------|---------|-----------|
| FIX-NW-01 | NEWAVE original | `newave/newave-caso-reduzido/` | Caso NEWAVE estocástico válido |
| FIX-NW-02 | NEWAVE convertido | `newave/cobre-caso-reduzido/` | Gabarito da conversão de FIX-NW-01 |
| FIX-NW-03 | NEWAVE-determ original | `newave-determ/newave-set-24-reduzido-calibrado-determ-2000/` | Caso NEWAVE determinístico válido |
| FIX-NW-04 | NEWAVE-determ convertido | `newave-determ/cobre-set-24-reduzido-calibrado-determ-2000/` | Gabarito da conversão de FIX-NW-03 |
| FIX-DC-01 | DECOMP original | `decomp/decomp-mar-26-rv2-reduzido/` | Caso DECOMP válido |
| FIX-DC-02 | DECOMP convertido | `decomp/cobre-mar-26-rv2-reduzido/` | Gabarito da conversão de FIX-DC-01 |

---

## 1. bridge_check_newave

**Descrição:** Valida se um deck NEWAVE original está bem formado (antes de converter).

**Input:** `src` (caminho do caso NEWAVE)

**Output esperado:**
- `status`: "ok" ou "error"
- `verdict`: "OK", "WARNINGS" ou "WILL_NOT_CONVERT"
- `checks`: lista de verificações realizadas
- `diagnostics`: lista de problemas encontrados

### Testes de Integração

Testam se a **comunicação MCP está funcionando**, não se a lógica do check está correta.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-CHK-NW-01 | Tool é chamada e retorna envelope válido | FIX-NW-01 | `status` existe, é string | Verifica que a tool responde algo válido (não crashou, não retornou null) |
| I-CHK-NW-02 | Tool aceita caminho absoluto | FIX-NW-01 (abs) | `status: ok` | Garante que aceita caminhos absolutos (básico, mas importante) |
| I-CHK-NW-03 | Tool rejeita caminho fora do workspace | `/etc/passwd` | `status: error` | Testa a **segurança**: a tool não deve acessar arquivos fora do workspace configurado |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer** com casos válidos.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| F-CHK-NW-01 | Valida caso NEWAVE estocástico válido | FIX-NW-01 | `status: ok`, `verdict: OK` | Caso principal: NEWAVE estocástico válido deve passar. Se esse falha, a tool tá quebrada. |
| F-CHK-NW-02 | Valida caso NEWAVE determinístico válido | FIX-NW-03 | `status: ok`, `verdict: OK` | Confirma que NEWAVE determinístico também funciona (pode ter diferenças de arquivos/switches) |
| F-CHK-NW-03 | Retorna lista de checks realizados | FIX-NW-01 | `checks` é lista não-vazia | Verifica que retorna a **lista de checks** feitos (útil pro usuário entender o que foi validado) |
| F-CHK-NW-04 | Identifica arquivos obrigatórios presentes | FIX-NW-01 | check "Required files present" passed | Verifica um check específico: "Required files present" deve estar passando |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**. São os mais importantes pra garantir que o check é útil!

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-CHK-NW-01 | Detecta caso.dat ausente | FIX-NW-ERR-01 | `status: error`, diagnostics menciona "caso.dat" | `caso.dat` é o **ponto de entrada** do NEWAVE. Sem ele, nada funciona. |
| E-CHK-NW-02 | Detecta dger.dat ausente | FIX-NW-ERR-02 | `status: error`, diagnostics menciona "dger.dat" | `dger.dat` tem os **switches** e configurações principais. Sem ele, não dá pra validar o resto. |
| E-CHK-NW-03 | Detecta hidr.dat ausente | FIX-NW-ERR-03 | `status: error`, diagnostics menciona "hidr.dat" | `hidr.dat` é **binário obrigatório** (dados das hidrelétricas). Erro comum: esquecer de copiar. |
| E-CHK-NW-04 | Detecta vazoes.dat ausente | FIX-NW-ERR-04 | `status: error`, diagnostics menciona "vazoes.dat" | `vazoes.dat` é **binário obrigatório** (séries de vazões). Mesmo caso. |
| E-CHK-NW-05 | Detecta dger.dat corrompido | FIX-NW-ERR-05 | `status: error`, diagnostics menciona parse/dger | Arquivo **corrompido** é diferente de ausente. O check deve dar erro de parse, não "arquivo não encontrado". |
| E-CHK-NW-06 | Detecta diretório vazio | FIX-NW-ERR-06 | `status: error`, diagnostics menciona "caso.dat" | **Diretório vazio** é um caso edge comum (usuário aponta pro diretório errado). |
| E-CHK-NW-07 | Rejeita caminho inexistente | `/caminho/inexistente` | `status: error` | Caminho **inexistente** deve dar erro claro, não exceção genérica. |
| E-CHK-NW-08 | Rejeita arquivo (não diretório) | arquivo.txt | `status: error` | Usuário passa **arquivo** em vez de diretório — deve rejeitar com mensagem clara. |

---

## 2. bridge_check_decomp

**Descrição:** Valida se um deck DECOMP original está bem formado (antes de converter).

**Input:** `src` (caminho do caso DECOMP)

**Output esperado:** Similar a bridge_check_newave

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-CHK-DC-01 | Tool é chamada e retorna envelope válido | FIX-DC-01 | `status` existe | Verifica que a tool responde algo válido |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer** com casos válidos.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| F-CHK-DC-01 | Valida caso DECOMP válido | FIX-DC-01 | `status: ok`, `verdict: OK` | Caso principal: DECOMP válido deve passar |
| F-CHK-DC-02 | Retorna lista de checks realizados | FIX-DC-01 | `checks` é lista não-vazia | Verifica que retorna os checks feitos |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-CHK-DC-01 | Detecta dadger ausente | FIX-DC-ERR-01 | `status: error`, menciona "dadger" | `dadger.rvX` é o ponto de entrada do DECOMP |
| E-CHK-DC-02 | Detecta dadger corrompido | FIX-DC-ERR-02 | `status: error`, erro de parse | Arquivo corrompido deve dar erro de parse claro |
| E-CHK-DC-03 | Rejeita caminho inexistente | `/inexistente` | `status: error` | Caminho inexistente deve dar erro claro |

---

## 3. bridge_convert_newave

**Descrição:** Converte um caso NEWAVE original para formato COBRE.

**Input:** `src`, `dst`, `validate`, `force`, `dry_run`

**Output esperado:**
- `status`: "ok" ou "error"
- `artifacts.deck`: caminho do deck gerado (quando não dry_run)

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-CNV-NW-01 | Tool é chamada com parâmetros corretos | FIX-NW-01, dst=temp | `status` existe | Verifica que a tool aceita os parâmetros e responde |
| I-CNV-NW-02 | dry_run não cria arquivos | FIX-NW-01, dry_run=True | `status: ok`, dst não existe | Garante que `dry_run` realmente não escreve nada |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-CNV-NW-01 | Converte caso estocástico | FIX-NW-01 → temp | `status: ok`, compara com FIX-NW-02 | Gabarito | **Teste principal**: conversão deve gerar resultado idêntico ao gabarito |
| F-CNV-NW-02 | Converte caso determinístico | FIX-NW-03 → temp | `status: ok`, compara com FIX-NW-04 | Gabarito | Confirma que determinístico também converte corretamente |
| F-CNV-NW-03 | validate=True valida após conversão | FIX-NW-01, validate=True | `status: ok` | - | Garante que o deck gerado é válido automaticamente |
| F-CNV-NW-04 | Conversão via MCP = conversão via CLI | FIX-NW-01 | output MCP == output CLI direto | Gabarito | Garante que a camada MCP não introduz diferenças |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-CNV-NW-01 | Rejeita src inexistente | `/inexistente` | `status: error` | Caminho inexistente deve dar erro claro |
| E-CNV-NW-02 | Rejeita dst existente sem force | dst já existe | `status: error` | Proteção contra sobrescrita acidental |
| E-CNV-NW-03 | Aceita dst existente com force=True | dst existe, force=True | `status: ok` | Confirma que `force` permite sobrescrever |
| E-CNV-NW-04 | Falha com caso quebrado | FIX-NW-ERR-01 | `status: error` | Conversão de caso inválido deve falhar, não crashar |

---

## 4. bridge_convert_decomp

**Descrição:** Converte um caso DECOMP original para formato COBRE.

**Input:** `src`, `dst`, `validate`, `force`, `dry_run`

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-CNV-DC-01 | Tool é chamada corretamente | FIX-DC-01, dry_run=True | `status` existe | Verifica que a tool aceita os parâmetros e responde |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-CNV-DC-01 | Converte caso DECOMP | FIX-DC-01 → temp | `status: ok`, compara com FIX-DC-02 | Gabarito | **Teste principal**: conversão deve gerar resultado idêntico ao gabarito |
| F-CNV-DC-02 | Conversão via MCP = conversão via CLI | FIX-DC-01 | output MCP == output CLI direto | Gabarito | Garante que a camada MCP não introduz diferenças |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-CNV-DC-01 | Rejeita src inexistente | `/inexistente` | `status: error` | Caminho inexistente deve dar erro claro |
| E-CNV-DC-02 | Falha com caso quebrado | FIX-DC-ERR-01 | `status: error` | Conversão de caso inválido deve falhar, não crashar |

---

## 5. bridge_compare_newave

**Descrição:** Compara resultados de uma rodada NEWAVE contra a saída COBRE.

**Input:** `newave_dir`, `cobre_dir`, `tolerance`, `fmt`

**Output esperado:**
- `status`: "ok" ou "error"
- `identical`: boolean (se os resultados são idênticos)
- `diffs`: lista de diferenças (quando não idênticos)

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-CMP-NW-01 | Tool é chamada corretamente | FIX-NW-01, FIX-NW-02 | `status` existe | Verifica que a tool aceita dois diretórios e responde |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-CMP-NW-01 | Compara original vs convertido (iguais) | FIX-NW-01 vs FIX-NW-02 | `identical: true` ou diffs conhecidos | Gabarito | **Teste principal**: comparar caso original com seu gabarito convertido |
| F-CMP-NW-02 | Detecta diferenças quando há | FIX-NW-01 vs FIX-NW-02-modificado | `identical: false`, `diffs` não-vazio | Gabarito | Garante que diferenças reais são detectadas |
| F-CMP-NW-03 | Tolerance afeta resultado | tolerance=0.01 vs tolerance=0.0001 | resultados diferentes | - | Confirma que o parâmetro tolerance funciona |
| F-CMP-NW-04 | fmt=json retorna JSON | fmt=json | output é JSON parseável | - | Verifica que o formato de saída funciona |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-CMP-NW-01 | Rejeita newave_dir inexistente | `/inexistente`, FIX-NW-02 | `status: error` | Primeiro argumento inválido deve dar erro claro |
| E-CMP-NW-02 | Rejeita cobre_dir inexistente | FIX-NW-01, `/inexistente` | `status: error` | Segundo argumento inválido deve dar erro claro |

---

## 6. bridge_compare_decomp

**Descrição:** Compara resultados de uma rodada DECOMP contra a saída COBRE.

**Input:** `decomp_dir`, `cobre_dir`, `tolerance`, `fmt`

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-CMP-DC-01 | Tool é chamada corretamente | FIX-DC-01, FIX-DC-02 | `status` existe | Verifica que a tool aceita dois diretórios e responde |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-CMP-DC-01 | Compara original vs convertido | FIX-DC-01 vs FIX-DC-02 | `identical: true` ou diffs conhecidos | Gabarito | **Teste principal**: comparar caso original com seu gabarito convertido |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-CMP-DC-01 | Rejeita caminhos inexistentes | `/inexistente` | `status: error` | Caminhos inválidos devem dar erro claro |

---

## 7. deck_list

**Descrição:** Lista os arquivos de um deck COBRE (json/parquet).

**Input:** `case_dir`

**Output esperado:**
- `status`: "ok" ou "error"
- `count`: número de arquivos
- `files`: lista de {path, rel, kind, bytes}

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-DL-01 | Tool é chamada corretamente | FIX-NW-02 | `status` existe | Verifica que a tool aceita um diretório e responde |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-DL-01 | Lista arquivos de deck NEWAVE | FIX-NW-02 | `count > 0`, `files` contém json/parquet | - | Caso básico: listar um deck válido |
| F-DL-02 | Lista arquivos de deck DECOMP | FIX-DC-02 | `count > 0` | - | Confirma que funciona com DECOMP também |
| F-DL-03 | Conta arquivos corretamente | FIX-NW-02 | `count` == número real de arquivos | Gabarito | Verifica que a contagem está correta |
| F-DL-04 | Retorna tamanhos corretos | FIX-NW-02 | `bytes` de cada arquivo == tamanho real | Gabarito | Verifica que os metadados estão corretos |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-DL-01 | Rejeita caminho inexistente | `/inexistente` | `status: error` | Caminho inexistente deve dar erro claro |
| E-DL-02 | Rejeita arquivo (não diretório) | arquivo.txt | `status: error` | Deve rejeitar arquivo quando espera diretório |

---

## 8. deck_read_parquet

**Descrição:** Lê uma amostra de um arquivo Parquet do deck.

**Input:** `path`, `columns` (opcional), `limit` (opcional)

**Output esperado:**
- `status`: "ok" ou "error"
- `nrows`: número total de linhas
- `columns`: lista de colunas
- `dtypes`: tipos de cada coluna
- `head`: amostra das primeiras linhas

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-DRP-01 | Tool é chamada corretamente | hydro_geometry.parquet | `status` existe | Verifica que a tool aceita um arquivo e responde |
| I-DRP-02 | Aceita parâmetro columns | columns=["hydro_id"] | `status: ok` | Verifica que parâmetros opcionais funcionam |
| I-DRP-03 | Aceita parâmetro limit | limit=5 | `head` tem 5 elementos | Verifica que limit é respeitado |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-DRP-01 | Lê hydro_geometry corretamente | hydro_geometry.parquet | `nrows: 8869`, `columns: [hydro_id, volume_hm3, height_m, area_km2]` | Gabarito | Verifica valores exatos conhecidos |
| F-DRP-02 | Lê hydro_energy_productivity | hydro_energy_productivity.parquet | `nrows: 7213` | Gabarito | Confirma com outro arquivo |
| F-DRP-03 | Filtra colunas corretamente | columns=["hydro_id"] | `head[0]` só tem `hydro_id` | Gabarito | Verifica que filtro de colunas funciona |
| F-DRP-04 | Limit funciona | limit=3 | `len(head) == 3` | - | Verifica que limit limita corretamente |
| F-DRP-05 | Valores da primeira linha | hydro_geometry.parquet | `head[0].hydro_id == 0` | Gabarito | Verifica valor específico conhecido |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-DRP-01 | Rejeita arquivo inexistente | `/inexistente.parquet` | `status: error` | Arquivo inexistente deve dar erro claro |
| E-DRP-02 | Rejeita coluna inexistente | columns=["coluna_fake"] | `status: error` | Coluna inválida deve dar erro claro |
| E-DRP-03 | Rejeita arquivo não-parquet | arquivo.json | `status: error` | Tipo de arquivo errado deve ser rejeitado |

---

## 9. deck_describe_parquet

**Descrição:** Retorna estatísticas de um arquivo Parquet.

**Input:** `path`

**Output esperado:**
- `status`: "ok" ou "error"
- `nrows`: número de linhas
- `ncols`: número de colunas
- `dtypes`: tipos de cada coluna
- `describe`: estatísticas (min, max, mean, etc.)

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-DDP-01 | Tool é chamada corretamente | hydro_geometry.parquet | `status` existe | Verifica que a tool aceita um arquivo e responde |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-DDP-01 | Descreve hydro_geometry | hydro_geometry.parquet | `nrows: 8869`, `ncols: 4` | Gabarito | Verifica valores exatos conhecidos |
| F-DDP-02 | Retorna dtypes corretos | hydro_geometry.parquet | `dtypes.hydro_id: Int32` | Gabarito | Verifica que tipos estão corretos |
| F-DDP-03 | Retorna estatísticas | hydro_geometry.parquet | `describe` contém min, max, mean | - | Verifica que estatísticas são calculadas |
| F-DDP-04 | Valores estatísticos corretos | hydro_geometry.parquet | `describe.min.hydro_id == 0` | Gabarito | Verifica valor específico conhecido |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-DDP-01 | Rejeita arquivo inexistente | `/inexistente.parquet` | `status: error` | Arquivo inexistente deve dar erro claro |

---

## 10. deck_edit_parquet

**Descrição:** Edita células de um Parquet preservando o schema.

**Input:** `path`, `where`, `set_values`, `dry_run`

**Output esperado:**
- `status`: "ok" ou "error"
- `matched_rows`: quantas linhas casaram com `where`
- `written`: boolean (se gravou ou não)

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-DEP-01 | Tool é chamada corretamente | hydro_geometry, where, set_values | `status` existe | Verifica que a tool aceita os parâmetros e responde |
| I-DEP-02 | dry_run não modifica arquivo | dry_run=True | arquivo não muda | **Crítico**: garante que dry_run é seguro |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-DEP-01 | dry_run retorna matched_rows correto | where={hydro_id: 1} | `matched_rows >= 1` | - | Verifica que o filtro funciona sem modificar |
| F-DEP-02 | Edição real muda valor | where={hydro_id: 1}, set_values={volume_hm3: 999} | Reler e verificar valor mudou | Gabarito | **Teste principal**: verifica que edição funciona |
| F-DEP-03 | Schema é preservado após edição | editar e reler | dtypes iguais antes/depois | Gabarito | **Crítico**: edição não deve corromper o arquivo |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-DEP-01 | Rejeita arquivo inexistente | `/inexistente.parquet` | `status: error` | Arquivo inexistente deve dar erro claro |
| E-DEP-02 | Rejeita coluna inexistente em where | where={coluna_fake: 1} | `status: error` | Filtro com coluna inválida deve falhar |
| E-DEP-03 | Rejeita coluna inexistente em set_values | set_values={coluna_fake: 1} | `status: error` | Edição de coluna inválida deve falhar |

---

## 11. docs_list

**Descrição:** Lista páginas da documentação do COBRE.

**Input:** `section` (opcional)

**Output esperado:**
- `status`: "ok" ou "error"
- `pages`: lista de páginas disponíveis

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-DOL-01 | Tool é chamada sem parâmetros | - | `status` existe | Verifica que a tool funciona sem parâmetros |
| I-DOL-02 | Tool aceita parâmetro section | section="reference" | `status: ok` | Verifica que parâmetro opcional funciona |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-DOL-01 | Lista todas as páginas | - | `pages` não-vazio | - | Caso básico: deve retornar alguma documentação |
| F-DOL-02 | Filtra por seção | section="reference" | todas as páginas são de "reference" | - | Verifica que filtro de seção funciona |
| F-DOL-03 | Seção inexistente retorna vazio | section="xyz123" | `pages` vazio ou `status: ok` | - | Seção inválida não deve crashar |

### Testes de Erro

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| (Nenhum teste de erro — esta tool não tem casos de erro esperados) | | | |

---

## 12. docs_read

**Descrição:** Lê uma página específica da documentação.

**Input:** `page`

**Output esperado:**
- `status`: "ok" ou "error"
- `content`: conteúdo da página (markdown)

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-DOR-01 | Tool é chamada corretamente | page="index" | `status` existe | Verifica que a tool aceita uma página e responde |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-DOR-01 | Lê página index | page="index" | `content` não-vazio | - | Caso básico: página principal deve existir |
| F-DOR-02 | Lê página de referência | page="reference/cli-reference" | `content` não-vazio | - | Confirma que páginas em subdiretórios funcionam |
| F-DOR-03 | Conteúdo contém título esperado | page="index" | `content` contém "COBRE" ou título | Contains | Verifica que o conteúdo faz sentido |
| F-DOR-04 | Conteúdo é markdown válido | page="index" | começa com "#" ou tem estrutura md | - | Verifica formato do conteúdo |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-DOR-01 | Rejeita página inexistente | page="pagina/fake/xyz" | `status: error` | Página inexistente deve dar erro claro |

---

## 13. results_convergence

**Descrição:** Retorna trajetória de convergência de um `cobre run`.

**Input:** `output_dir`, `tail` (opcional)

**Output esperado:**
- `status`: "ok" ou "error"
- `iterations`: lista das últimas iterações
- `final_gap`: gap final

**Dependência:** Precisa de output de `cobre run` (fixture FIX-RESULTS-01)

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-RC-01 | Tool é chamada corretamente | FIX-RESULTS-01 | `status` existe | Verifica que a tool aceita um diretório de resultados |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-RC-01 | Retorna iterações | FIX-RESULTS-01 | `iterations` não-vazio | - | Caso básico: deve retornar dados de convergência |
| F-RC-02 | tail limita resultado | tail=5 | `len(iterations) <= 5` | - | Verifica que parâmetro tail funciona |
| F-RC-03 | Valores são consistentes | FIX-RESULTS-01 | `final_gap` == gap da última iteração | Gabarito | Verifica consistência dos dados |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-RC-01 | Rejeita diretório sem convergence.parquet | diretório vazio | `status: error` | Diretório inválido deve dar erro claro |

---

## 14. results_query

**Descrição:** Query nos resultados de simulação.

**Input:** `output_dir`, `entity`, `columns`, `group_by`, `agg`, `scenario`, `limit`

**Output esperado:**
- `status`: "ok" ou "error"
- `rows`: dados retornados

**Dependência:** Precisa de output de `cobre run` (fixture FIX-RESULTS-01)

### Testes de Integração

Testam se a **comunicação MCP está funcionando**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| I-RQ-01 | Tool é chamada corretamente | entity="hydros" | `status` existe | Verifica que a tool aceita uma entity e responde |

### Testes Funcionais

Testam se a tool **faz o que deveria fazer**.

| ID | Descrição | Input | Validação | Método | Por que é importante |
|----|-----------|-------|-----------|--------|----------------------|
| F-RQ-01 | Query hydros retorna dados | entity="hydros" | `rows` não-vazio | - | Caso básico: query deve retornar dados |
| F-RQ-02 | Agregação funciona | group_by=["hydro_id"], agg="mean" | resultado agregado | - | Verifica que agregação é calculada |
| F-RQ-03 | Filtro por cenário funciona | scenario=1 | todos os rows são do cenário 1 | Gabarito | Verifica que filtro de cenário funciona |
| F-RQ-04 | limit limita resultado | limit=10 | `len(rows) <= 10` | - | Verifica que limit é respeitado |

### Testes de Erro

Testam se a tool **detecta problemas corretamente**.

| ID | Descrição | Input | Validação | Por que é importante |
|----|-----------|-------|-----------|----------------------|
| E-RQ-01 | Rejeita entity inexistente | entity="xyz_fake" | `status: error` | Entity inválida deve dar erro claro |
| E-RQ-02 | Rejeita agg inválido | agg="invalid_agg" | `status: error` | Agregação inválida deve dar erro claro |

---

## Resumo de Contagem

| Categoria | Quantidade |
|-----------|------------|
| Testes de Integração (I-xxx) | ~25 |
| Testes Funcionais (F-xxx) | ~45 |
| Testes de Erro (E-xxx) | ~35 |
| **Total** | **~105** |

### Por Tool

| Tool | I | F | E | Total |
|------|---|---|---|-------|
| bridge_check_newave | 3 | 4 | 8 | 15 |
| bridge_check_decomp | 1 | 2 | 3 | 6 |
| bridge_convert_newave | 2 | 4 | 4 | 10 |
| bridge_convert_decomp | 1 | 2 | 2 | 5 |
| bridge_compare_newave | 1 | 4 | 2 | 7 |
| bridge_compare_decomp | 1 | 1 | 1 | 3 |
| deck_list | 1 | 4 | 2 | 7 |
| deck_read_parquet | 3 | 5 | 3 | 11 |
| deck_describe_parquet | 1 | 4 | 1 | 6 |
| deck_edit_parquet | 2 | 3 | 3 | 8 |
| docs_list | 2 | 3 | 0 | 5 |
| docs_read | 1 | 4 | 1 | 6 |
| results_convergence | 1 | 3 | 1 | 5 |
| results_query | 1 | 4 | 2 | 7 |

---

## Fixtures a Criar

### Prioridade Alta (necessárias para testes de erro)

1. **FIX-NW-ERR-01** — NEWAVE sem caso.dat
2. **FIX-NW-ERR-02** — NEWAVE sem dger.dat
3. **FIX-NW-ERR-05** — NEWAVE com dger.dat corrompido
4. **FIX-NW-ERR-06** — Diretório vazio

### Prioridade Média (para testes mais completos)

5. **FIX-NW-ERR-03** — NEWAVE sem hidr.dat
6. **FIX-NW-ERR-04** — NEWAVE sem vazoes.dat
7. **FIX-DC-ERR-01** — DECOMP sem dadger
8. **FIX-DC-ERR-02** — DECOMP corrompido

### Prioridade Baixa (resultados de cobre run)

9. **FIX-RESULTS-01** — Output de `cobre run` para testes de results_*

---

## Métodos de Validação

| Método | Descrição | Quando usar |
|--------|-----------|-------------|
| **Simples** | Verifica status e campos existem | Testes de integração |
| **Gabarito** | Compara com valor/arquivo conhecido | Testes funcionais com resposta determinística |
| **Contains** | Verifica substring no resultado | Documentação, mensagens de erro |
| **Judge (LLM)** | Avalia semanticamente se faz sentido | Conteúdo textual variável |

---

## Estratégia de Gabaritos

### Filosofia

Para tools que chamam `cobre` ou `cobre-bridge`, o teste valida se **a tool MCP produz o mesmo resultado que rodar o app diretamente na CLI**. Não estamos testando se o app funciona, mas se a tool MCP chama o app corretamente.

- **Setup (uma vez):** Rodar o CLI e salvar o output como fixture/gabarito
- **Teste (toda execução):** Tool MCP gera output → compara com gabarito

### Dependências por Tool

| Tool | Chama qual app? | Precisa instalar pra rodar teste? |
|------|-----------------|-----------------------------------|
| `bridge_check_newave` | cobre-bridge | ✅ Sim |
| `bridge_check_decomp` | cobre-bridge | ✅ Sim |
| `bridge_convert_newave` | cobre-bridge | ✅ Sim |
| `bridge_convert_decomp` | cobre-bridge | ✅ Sim |
| `bridge_compare_newave` | cobre-bridge | ✅ Sim |
| `bridge_compare_decomp` | cobre-bridge | ✅ Sim |
| `results_convergence` | Nenhum (só lê arquivos) | ❌ Não |
| `results_query` | Nenhum (só lê arquivos) | ❌ Não |
| `deck_list` | Nenhum | ❌ Não |
| `deck_read_parquet` | Nenhum | ❌ Não |
| `deck_describe_parquet` | Nenhum | ❌ Não |
| `deck_edit_parquet` | Nenhum | ❌ Não |
| `docs_list` | Nenhum | ❌ Não |
| `docs_read` | Nenhum | ❌ Não |

### Gabaritos: O que já temos vs O que precisamos gerar

#### ✅ Tools que JÁ TÊM gabarito (sem rodar nada)

| Tool | Gabarito disponível | Como validar |
|------|---------------------|--------------|
| `deck_list` | Arquivos em FIX-NW-02/FIX-DC-02 | Comparar lista retornada com listagem real do diretório |
| `deck_read_parquet` | Parquets já existem | Ler com polars e comparar valores exatos |
| `deck_describe_parquet` | Parquets já existem | Calcular stats com polars e comparar |
| `deck_edit_parquet` | Criar cópia temporária | Verificar se editou corretamente |
| `docs_list` | Lista de docs é estática | Listar arquivos .md da pasta de docs |
| `docs_read` | Docs são arquivos estáticos | Ler o .md direto e comparar conteúdo |
| `bridge_convert_newave` | FIX-NW-02 é o gabarito | Comparar output com fixture existente |
| `bridge_convert_decomp` | FIX-DC-02 é o gabarito | Comparar output com fixture existente |

#### ❌ Tools que PRECISAM rodar cobre-bridge pra gerar gabarito

| Tool | O que precisa gerar | Comando |
|------|---------------------|---------|
| `bridge_check_newave` | JSON de diagnóstico esperado | `cobre-bridge check newave <caso>` |
| `bridge_check_decomp` | JSON de diagnóstico esperado | `cobre-bridge check decomp <caso>` |
| `bridge_compare_newave` | JSON de diff esperado | `cobre-bridge compare newave <orig> <conv>` |
| `bridge_compare_decomp` | JSON de diff esperado | `cobre-bridge compare decomp <orig> <conv>` |

#### ❌ Tools que PRECISAM rodar cobre pra gerar gabarito

| Tool | O que precisa gerar | Comando |
|------|---------------------|---------|
| `results_convergence` | Output de convergência | `cobre run <caso_minimo>` → salvar parquets |
| `results_query` | Parquets de resultado | `cobre run <caso_minimo>` → salvar parquets |

### Resumo de Cobertura de Gabaritos

| Situação | Quantidade | % |
|----------|------------|---|
| ✅ Já tem gabarito | 8 tools | 57% |
| ❌ Precisa rodar cobre-bridge | 4 tools | 29% |
| ❌ Precisa rodar cobre | 2 tools | 14% |

### Fixtures Mínimas Necessárias

Para os testes serem rápidos e rodarem em qualquer máquina da empresa, precisamos de **casos mínimos**:

- **NEWAVE mínimo:** Caso reduzido que rode em segundos (poucos estágios, poucas usinas)
- **DECOMP mínimo:** Período mínimo possível
- **cobre run mínimo:** Poucas iterações, apenas pra ter output válido

Os casos `*-reduzido` que já temos nas fixtures devem servir pra isso.

---

## Fixtures a Criar

### Prioridade Alta (necessárias para testes de erro)

| ID | Descrição | Como criar |
|----|-----------|------------|
| FIX-NW-ERR-01 | NEWAVE sem caso.dat | Copiar FIX-NW-01 e deletar caso.dat |
| FIX-NW-ERR-02 | NEWAVE sem dger.dat | Copiar FIX-NW-01 e deletar dger.dat |
| FIX-NW-ERR-05 | NEWAVE com dger.dat corrompido | Copiar FIX-NW-01 e corromper dger.dat |
| FIX-NW-ERR-06 | Diretório vazio | Criar diretório vazio |

### Prioridade Média (para testes mais completos)

| ID | Descrição | Como criar |
|----|-----------|------------|
| FIX-NW-ERR-03 | NEWAVE sem hidr.dat | Copiar FIX-NW-01 e deletar hidr.dat |
| FIX-NW-ERR-04 | NEWAVE sem vazoes.dat | Copiar FIX-NW-01 e deletar vazoes.dat |
| FIX-DC-ERR-01 | DECOMP sem dadger | Copiar FIX-DC-01 e deletar dadger.rvX |
| FIX-DC-ERR-02 | DECOMP com dadger corrompido | Copiar FIX-DC-01 e corromper dadger |

### Prioridade Baixa (precisa de cobre rodando)

| ID | Descrição | Como criar |
|----|-----------|------------|
| FIX-RESULTS-01 | Output de `cobre run` | Rodar cobre num caso mínimo e salvar output |

---

## Próximos Passos

1. [ ] Criar fixtures quebradas (FIX-NW-ERR-*, FIX-DC-ERR-*) — só copiar e deletar arquivos
2. [ ] Gerar gabaritos das tools `bridge_check_*` e `bridge_compare_*` — precisa rodar cobre-bridge
3. [ ] Gerar gabarito FIX-RESULTS-01 — precisa rodar cobre
4. [ ] Implementar validação por gabarito no framework (comparar arquivos/JSONs)
5. [ ] Implementar testes funcionais com gabarito pras 8 tools que já dá
6. [ ] Implementar testes de erro usando fixtures quebradas
7. [ ] (Opcional) Integrar Judge LLM para testes semânticos de docs
