# Auditoria da Base — Sprint 4 (Issue #1)

Data: 2026-09-11 · Ambiente: Windows 11, Python 3.14.3, venv novo a partir de `requirements.txt`

Verificação executada de ponta a ponta na base importada da Sprint 3: suite de testes, ETL completo (`pipeline.py` → `load_to_sql.py`), boot da API (`uvicorn start_api:app`), simulador de telemetria, endpoints `GET` (resumo-frota, alertas, telemetria, equipamentos) e boot do dashboard Streamlit. Inclui **clone limpo do zero** (reproduzindo o fluxo de quem baixa o repo pela primeira vez).

## 1. Resultado geral

| Etapa | Resultado | Observação |
|---|---|---|
| `pip install -r requirements.txt` | ⚠️ quebra a suite | passlib 1.7.4 × bcrypt ≥ 4.1 incompatíveis (ver B1) |
| `pytest tests/` | ✅ 21/21 com fix | 13 falham sem fix, 51 warnings |
| ETL do zero (clone limpo) | ✅ | schema + seed + 1000 registros + features + scaler — **só roda com `cwd=src/data`** (imports planos, ver B4) |
| ETL re-executado sobre base existente | 🔴 insere 0 registros e reporta `[OK]` | ver B2 |
| Boot da API | ✅ | via `uvicorn start_api:app` |
| Simulador + POST telemetria | ✅ | com URL corrigida (ver B3) |
| RBAC (operador × equipamento errado) | ✅ 403 | comportamento correto |
| GETs autenticados | ✅ | resumo-frota, alertas, telemetria, me, equipamentos |
| Dashboard Streamlit | ✅ boot, HTTP 200 | não validado visualmente nesta auditoria |
| Login JWT / expiração 60min / bcrypt hash | ✅ | |

## 2. Lacunas do feedback do tutor — localização exata no código

| Lacuna | Onde está | Detalhe |
|---|---|---|
| Score fixo por classe | `src/ml/predictor.py:13` (`SCORE_POR_NIVEL`) e `:81` | `score = SCORE_POR_NIVEL.get(nivel, 50)` — todo "Alto" vale 63, todo "Crítico" 88. Confirmado na saída do simulador: 63/38/88 em todas as execuções. As `probabilidades` já são calculadas e persistidas (`predictor.py:72-92`) — base pronta para score contínuo. |
| Fatores não refletem a decisão | `src/ml/predictor.py:40-56` (`_extrair_top_features`) | **Pior do que o tutor descreveu**: não é contribuição nem global — é o **valor absoluto bruto** das variáveis de telemetria. `proximidade_agua_m` (0–1000 m) e `horas_uso_equipamento` (~milhares) sempre vencem `umidade_solo_pct` (~0–100). Umidade alta com proximidade 500 m ainda reporta proximidade como "fator". |
| Sem prints do painel | ausência de `assets/prints/` | n/a — alocado na issue #7 |
| Vídeo só visão do operador | processo | alocado na issue #9 |

## 3. Bugs e dívidas encontrados (novos, além do feedback)

- **B1 — requirements quebra a suite em ambiente novo (reprodutibilidade).** `passlib[bcrypt]>=1.7.4` instala bcrypt 5.x; o bcrypt novo lança `ValueError: password cannot be longer than 72 bytes` ao hashear/verificar senha via passlib 1.7.4 (sem manutenção desde 2020). 13/21 testes falham num `pip install` limpo. Fix validado no audit: pin `bcrypt==4.0.1` → 21/21 passam. Decisão para #2: pin `bcrypt==4.0.1` ou migrar auth para `pwdlib`.
- **B2 — ETL silenciosamente perde dados na re-execução.** `features.csv` carrega a coluna `id_registro`; `preparar_dataframe` (`src/data/load_to_sql.py:78-88`) não a exclui (só exclui se a coluna NÃO existir na tabela — lógica invertida) e o insert usa `INSERT OR IGNORE`. Em base já populada, os `id_registro` 1..1000 do dataset colidem com PKs existentes → **0 registros inseridos** e o pipeline imprime `[OK] Pipeline concluído`. Zero dados novos sem nenhum erro. Confirmado: 1016 linhas antes e depois da re-execução; no clone limpo insere 1000 normalmente. Correção na #3: dropar `id_registro` na carga e falhar (ou alertar) quando `inseridos == 0`.
- **B3 — Simulador quebra com a URL documentada.** `simulador_telemetria.py` monta `{base_url}/login` e `{base_url}/telemetria`, mas as rotas vivem sob `/api/v1`. `--base-url http://127.0.0.1:8000` → 404. Funciona apenas com `--base-url http://127.0.0.1:8000/api/v1`. Fix na #2 (juntar prefixo no simulador).
- **B4 — Imports frágeis no ETL.** `src/data/pipeline.py:10-11` usa imports planos (`from feature_engineering import ...`) que só resolvem com `cwd=src/data`. Rodar como módulo (`python -m src.data.pipeline`) quebra. Padronizar na #2.
- **B5 — `sompo.db` não é rastreado (`.gitignore: *.db`), mas clone da Sprint 3 o era.** Clone limpo não tem o banco — é obrigatório rodar o ETL antes de subir a API (funciona, validado; usuários demo vêm do `02_seed_data.sql`). Isso precisa estar explícito nas instruções de execução do README final (#9). Decidir também se o db de demonstração volta a ser rastreado ou se o ETL vira passo obrigatório documentado.
- **B6 — ETL suja a árvore git.** `pipeline.py` sobrescreve `src/data/scaler.pkl` (rastreado) a cada execução → `git status` sujo sem motivo. Ou o scaler sai do controle de versão, ou o pipeline não o regenera. Na #3.
- **B7 — `src/data/readme.md` defasado.** Diz "Scripts a implementar na Sprint 2" para scripts que existem e rodam. Atualizar na #9 (documentação).
- **B8 — `start_api.py` não sobe servidor sozinho.** É só um import (`__all__ = ["app"]`); rodar `python start_api.py` não faz nada (confirmado: processo sai na hora). README final deve padronizar `uvicorn start_api:app --reload`. Na #9.
- **B9 — 51 warnings na suite** (passlib deprecações etc.). Baixa prioridade; limpar na #8 quando a suite crescer.
- **B10 — Secret JWT com fallback de desenvolvimento.** `src/security/auth.py:16-25`: sem `JWT_SECRET_KEY` no ambiente, o token é assinado com `agrorisk-dev-secret-change-me-32b` (apenas um `RuntimeWarning`). A API sobe e autentica normalmente com o secret padrão — em "condição de uso" o sistema opera com chave conhecida publicamente. Na #6: falhar o boot sem a variável (ou gerar secret local persistido em `.env`).
- **B11 — Dois scores com semânticas distintas expostos na mesma resposta.** `src/api/telemetria_service.py:108-112` calcula `score_risco` contínuo (heurística `score_regra`, 0-100) e, em paralelo, `score_risco_predito` **fixo por classe** (via modelo, seção 2). O mesmo payload devolve `81 (Crítico)` de regra e `63 (Alto)` do modelo para o mesmo registro — níveis diferentes para o mesmo evento, sem explicação. A #4 deve reconciliar: score do modelo contínuo derivado das probabilidades (mesma escala 0-100 da regra), com o papel de cada um documentado.

## 4. Pontos fortes confirmados (manter — tutor elogiou)

Simulador autenticado em fluxo contínuo; contrato Pydantic validado; RF carregado uma única vez no lifespan; predição + alerta na mesma transação com `commit` único; RBAC operador×equipamento (403 verificado); auditoria com IP; banco com views e gatilho de consistência; 21 testes com banco temporário via `conftest.py`; diagrama fiel; divisão por issues.

## 5. Consequências para as issues seguintes

- **#2 (REFACT)**: B1 (bcrypt), B3 (URL simulador), B4 (imports ETL) — todos são "fluxo estável e reproduzível".
- **#3 (ETL/BANCO)**: B2 é o achado mais grave (perda silenciosa de dados); B5, B6.
- **#4 (ML)**: score contínuo + fatores reais já têm base pronta (probabilidades persistidas); B11 (reconciliar score de regra × score do modelo).
- **#6 (SEGURANÇA)**: B10 (secret JWT com fallback de dev).
- **#8 (MVP)**: B9 (warnings).
- **#9 (ENTREGA)**: B5/B7/B8 — instruções de execução precisam do passo ETL obrigatório (`cd src/data && python pipeline.py`) antes do `uvicorn start_api:app`, já que `sompo.db` não é versionado.

A ordem de execução #1 → #2 → ... se mantém válida.

## 6. Notas de auditoria

- O `sompo.db` local (não rastreado) foi tocado durante a auditoria: o simulador inseriu 3 registros de telemetria (ids 1014-1016) e 2 alertas (ids 8-9) via API. Sem impacto no repositório; removíveis com um re-run do ETL sobre base zerada, se desejado.
- O simulador não aborta o lote ao receber 403 de RBAC — imprime `ERRO HTTP` por registro e continua (comportamento observado com `--role operador`).