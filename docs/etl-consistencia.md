# Consistência do ETL e do banco — Sprint 4 (issue #3)

Evidência das correções de integridade da carga: o que foi encontrado, o que mudou e o
resultado observado rodando de verdade. Complementa o diagnóstico em
[`auditoria-sprint4.md`](auditoria-sprint4.md).

## O que estava errado

| ID | Problema | Consequência |
|----|----------|--------------|
| B2 | `preparar_dataframe` inseria a PK `id_registro` da planilha; `INSERT OR IGNORE` engolia a colisão de PK | Em base já populada a carga **inseria 0 registros e imprimia `[OK]`** |
| — | `INSERT OR IGNORE` tolerava **qualquer** violação (CHECK, NOT NULL, FK), não só duplicidade | Linha ruim sumia em silêncio; a carga "funcionava" sem carregar |
| — | `alerta_gerado` convertido com `astype(bool)` | Se a fonte trouxesse `"0"`/`"1"`, tudo viraria `True` — e o gatilho `trg_valida_alerta` recusaria o lote |
| — | Dados sujos chegavam direto ao `executemany` | Um `NaN` ou um valor fora de faixa **abortava o lote no meio** (constraint/gatilho) |
| — | Sem chave de origem | Não havia como saber de qual coleta um registro veio, nem recarregar sem duplicar |
| B6 | `pipeline.py` reescrevia `src/data/scaler.pkl` (rastreado) | `git status` sujo a cada execução |

Reprodução do B2 na base da Sprint 3 (cópia do `sompo.db`, 1.018 registros):

```
1a carga: 0 -> total 1018
2a carga: 0 -> total 1018
```

## O que mudou

1. **Rastreabilidade na `telemetria`** (`src/sql/01_schema.sql`): colunas `fonte` e `id_coleta`,
   com `UNIQUE (fonte, id_coleta)`. O ETL grava `fonte='dataset_simulado'` e `id_coleta` = linha
   da planilha; a API grava `fonte='api'` explicitamente e deixa `id_coleta` nulo (coleta ao vivo
   não tem id de origem). `id_registro` segue sendo a PK do banco, atribuída pelo banco.
2. **Migração de bases antigas** (`pipeline.atualizar_schema_legado`): `CREATE TABLE IF NOT EXISTS`
   não altera tabela existente — um `sompo.db` anterior ganha as colunas **antes** dos arquivos SQL
   (senão o índice do schema novo não aplica). As linhas que já existiam ficam com `fonte='legado'`,
   não `'api'`: procedência desconhecida não vira procedência inventada.
3. **Higienização antes do banco** (`src/data/validacao_dados.py`): schema, tipos, faltantes,
   duplicidades, domínios, faixas (incluindo temperatura e coordenadas) e a regra do gatilho
   (alerta só para Alto/Crítico) são checados com o motivo de cada descarte no relatório.
   O id de coleta (`id_registro`) é obrigatório: sem ele não há rastreabilidade.
4. **Carga idempotente** (`src/data/load_to_sql.py`): pula coleta já carregada (`fonte`+`id_coleta`)
   e medição já registrada no mesmo equipamento/instante — reimportar não acumula duplicata.
5. **`INSERT` puro no lugar de `INSERT OR IGNORE`**: o que o banco recusa agora **aparece** como
   erro, em vez de virar carga silenciosa de 0 registros.
6. **Conexão única** (`src/data/conexao.py`): `PRAGMA foreign_keys` + `busy_timeout` de 5 s
   (retry nativo do SQLite para escrita concorrente), usada pelo ETL e pela API.
7. **B6 resolvido**: `scaler.pkl` e `label_encoders.pkl` são artefatos gerados — saíram do
   versionamento e entraram no `.gitignore`.

## Evidências

### Pipeline de ponta a ponta, duas vezes sobre a mesma fonte

```
=== EXECUCAO 1 ===
[OK] Schema executado em sompo.db
[OK] 1000 registros brutos salvos em data/raw/dataset_simulado.csv
[OK] Features salvas em data/processed/features.csv
[OK] Carga: 997 inseridos, 0 coletas já presentes, 0 medições já registradas, descartados por qualidade (duplicado=3)
[OK] Pipeline concluído com sucesso (997 registros em telemetria).

=== EXECUCAO 2 (mesma fonte) ===
[OK] Carga: 0 inseridos, 997 coletas já presentes, 0 medições já registradas, descartados por qualidade (duplicado=3)
[OK] Pipeline concluído com sucesso (997 registros em telemetria).
```

- Reexecutar **não duplica** (997 → 997) e diz exatamente o que fez: 997 coletas já presentes.
- O próprio dataset simulado tem 3 duplicidades de chave natural (mesmo equipamento no mesmo
  instante, 1.000 sorteios sobre 45 máquinas × 180 dias); elas são descartadas com motivo.

Estado do banco depois das duas execuções + 5 registros enviados pelo simulador pela API:

```
telemetria total      : 1002
por fonte             : {'api': 5, 'dataset_simulado': 997}
com rastreabilidade   : 997
duplicados equip+inst : 0
integrity/foreign_key : ok []
```

### Migração da base da Sprint 3 (1.018 registros, sem as colunas novas)

```
base da Sprint 3 - colunas: ['score_risco_calculado', 'diff_score', 'data_ingestao']
base da Sprint 3 - registros: 1018
[OK] Colunas de rastreabilidade adicionadas em telemetria
depois da migração - colunas: ['data_ingestao', 'fonte', 'id_coleta']
procedência das linhas antigas: {'legado': 1018}
índice único criado: ['idx_telemetria_rastreabilidade', ...]
registros preservados: 1018
```

### Dataset sujo não corrompe o banco

Fonte com 10 linhas (4 íntegras + 6 sujas: faltante, duplicada, fora de faixa ×2, fora do
domínio e incoerente com o gatilho), carregada sobre uma cópia do banco:

```
descartadas por motivo  : {'faltante': 1, 'duplicado': 1, 'dominio_invalido': 1, 'fora_de_range': 2, 'inconsistente': 1}
inseridos               : 4
telemetria antes/depois : 1002 -> 1006
id_coleta carregados    : [9001, 9002, 9003, 9004]
duplicados equip+inst   : 0
integrity_check         : ok | foreign_key_check: []
```

As 6 linhas ruins saem com motivo; as 4 boas entram; a base segue íntegra (sem meia carga).

### Regressão automatizada

`tests/test_etl.py` cobre cada comportamento acima, incluindo a regressão do B2 (recarga não
insere 0 nem duplica), a recusa que antes era engolida pelo `INSERT OR IGNORE`, a migração de
base legada, o descarte por motivo e o alinhamento entre os domínios da higienização e os `CHECK`
do schema.

```
44 passed
```

## Decisões

- **Duplicidade por equipamento + instante é tratada na carga, não por constraint.** Um
  `UNIQUE (id_equipamento, data_hora)` no schema também cobriria a coleta ao vivo, mas
  transformaria um POST repetido na API em erro 500. A validação da coleta (e a resposta
  adequada a um POST duplicado) é escopo da issue #5.
- **`id_coleta` nulo na telemetria da API é intencional**: coleta ao vivo não tem id de origem, e
  o registro continua rastreável por `fonte`, equipamento e timestamp. Um id de coleta
  informado pelo cliente entra na #5, junto com a validação da coleta.
- **`fonte` na base legada é `'legado'`** — as linhas migradas perdem o `id_coleta`
  original (não há como reconstruí-lo), mas não ganham procedência falsa.
- **`sompo.db` continua fora do versionamento** (B5): clone limpo roda o ETL antes de subir a
  API. As instruções ficam no README final (#9).
- **A base demo foi reconstruída** com a estrutura final; a anterior está preservada em
  `C:\FIAP Repos\backup-sompo-antes-sprint4.db` (fora do repositório).
