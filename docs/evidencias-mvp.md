# Evidências do MVP — Sprint 4 (issue #8)

Prova de que o MVP integrado funciona ponta a ponta: entrada de telemetria → banco → modelo →
score → alerta/relatório → auditoria, com a suite verde e as leituras de volta pela API.

## 1. Suite de testes

```
python -m pytest tests/ -q
80 passed, 2 warnings in 25.24s
```

| Arquivo | Casos | Cobre |
|---|---|---|
| `tests/test_unit.py` | 23 | Funções puras de feature/score, **decomposição auditável da regra (`componentes_regra`)**, **mensagem do alerta com penalidades e segunda opinião**, score contínuo, fatores por contribuição, retry/retomada do simulador |
| `tests/test_api.py` | 38 | Login, RBAC, POST/GET telemetria, 409 de coleta repetida, payloads sujos, token expirado/forjado, auditoria, **alerta do histórico seguindo a regra mesmo divergindo** |
| `tests/test_etl.py` | 16 | Idempotência da carga, higienização por motivo, rastreabilidade, migração de base legada |
| `tests/test_e2e.py` | 3 | **Fluxo completo**: ETL em diretório temporário → API contra esse banco → score → alerta da regra no histórico → auditoria |
| `tests/conftest.py` | — | Banco temporário por teste, `TestClient`, segredo de teste fixo |

As 2 warnings restantes vêm de bibliotecas (deprecações do Starlette/anyio), não do projeto —
eram **65** antes desta sprint.

## 2. Execução demonstrativa de ponta a ponta

Banco regenerado do zero (`python src/data/pipeline.py` → 997 inseridos, 0 duplicados) com as
predições do dataset em lote (`python src/ml/04_predict.py`), API no ar e coleta simulada.

### Estado antes da coleta

```
telemetria          : 997   (fonte: dataset_simulado)
scores_modelo       : 997   (predição em lote sobre a base do ETL)
alertas             : 0
eventos de auditoria: 0
entradas sem score  : 0
```

### Coleta simulada (lote novo, 10 registros, sem intervalo)

```
python src/api/simulador_telemetria.py --n 10 --interval 0 --lote 501
EQ-GO-0006 -> 81 (Crítico) | predito 55 (Alto) | alerta SIM | divergente
EQ-PR-0025 -> 58 (Alto) | predito 33 (Médio) | alerta SIM | divergente
EQ-GO-0007 -> 100 (Crítico) | predito 81 (Crítico) | alerta SIM
EQ-PR-0023 -> 85 (Crítico) | predito 44 (Médio) | alerta SIM | divergente
EQ-PR-0023 -> 65 (Alto) | predito 60 (Alto) | alerta SIM
EQ-RS-0039 -> 77 (Crítico) | predito 18 (Baixo) | alerta SIM | divergente
EQ-MT-0017 -> 100 (Crítico) | predito 70 (Alto) | alerta SIM | divergente
EQ-MT-0003 -> 70 (Alto) | predito 41 (Médio) | alerta SIM | divergente
EQ-PR-0030 -> 75 (Alto) | predito 44 (Médio) | alerta SIM | divergente
EQ-BA-0035 -> 52 (Alto) | predito 14 (Baixo) | alerta SIM | divergente
Resumo: 10 enviados | 10 aceitos | 0 já registrados | 0 rejeitados pela API | 0 falhas de rede
```

Os 10 registros são Alto/Crítico **pela regra** — e os 10 geraram alerta, inclusive os 8 em que
o modelo discorda (antes, estes mostrariam `alerta NÃO` e nunca entrariam no histórico).

### Estado depois da coleta

```
telemetria          : 1007 (antes 997)       ← +10 exatos
  por fonte         : {'api': 10, 'dataset_simulado': 997}
scores_modelo       : 1007 (antes 997)
alertas             : 10 (antes 0)           ← 1 por coleta Alto/Crítico
eventos de auditoria: 21 (antes 0)
coletas do lote 501 : 10
entradas sem score  : 0                      ← toda entrada tem score
duplicados equip+hora: 0
integridade         : ok
```

**Coerência bidirecional regra↔histórico** (o defeito que motivou a fonte única):

```sql
SELECT COUNT(*) FROM telemetria t LEFT JOIN alertas a ON a.id_registro = t.id_registro
  WHERE t.fonte='api' AND t.alerta_gerado = 1 AND a.id_alerta IS NULL;   -- == 0
SELECT COUNT(*) FROM alertas a JOIN telemetria t ON a.id_registro = t.id_registro
  WHERE t.alerta_gerado = 0;                                              -- == 0
```

Ambas zero: tela, trilha e histórico discordam de ninguém.

### Decisão registrada pela trilha

```
2026-09-12T19:33:20 | Carlos Silva | decisao_risco |
  score_regra=58 nivel_regra=Alto score_modelo=33 nivel_modelo=Médio alerta=1 divergente=1
  fatores=velocidade_operacao_kmh,faixa_proximidade_encoded,historico_incidentes
```

`alerta=1` é a decisão da **regra**; `divergente=1` sinaliza o caso ambíguo ao auditor.

### Alerta emitido (penalidades da regra + segunda opinião)

```
EQ-PR-0025 | Alto | score 58 | Preventivo |
⚠️ Risco alto. Reduzir velocidade, evitar áreas alagadiças e monitorar condições do solo.
Fatores principais: declividade (16 pts), velocidade de operação (11 pts), umidade do solo (9 pts).
Segunda opinião do modelo: Médio (33) — caso divergente, inspecione as condições antes de confiar.
```

A mensagem cita as penalidades nomeadas da regra com os pontos de cada uma
(`ml.features.componentes_regra`) e o modelo como segunda opinião — não como decisão.

### Leituras de volta pela API (gestor e analista autenticados)

```
GET /resumo-frota            : 200 — 46 equipamentos
GET /equipamentos            : 50 equipamentos
GET /telemetria?limit=1      : EQ-MT-0023 | regra 58 Alto | modelo 33 Médio (divergente)
GET /alertas                 : 14 alertas
GET /equipamentos/EQ-BA-0035/risco : 200 — regra Alto × modelo Baixo
GET /auditoria?limit=3       : 3 eventos (último: consultar_risco de Fernanda Costa)
GET /health                  : {'status': 'ok', 'service': 'agrorisk-api', 'version': '3.0.0'}
```

## 3. Evidências visuais

Prints das três visões em [`assets/prints/`](../assets/prints) (capturados com o dashboard rodando
contra a API): gestor (mapa + tendências), operador (score regra × modelo + fatores) e analista
(alertas + trilha de auditoria). Detalhes em [`dashboard-relatorios.md`](dashboard-relatorios.md).

## 4. Casos de uso das User Stories

| ID | User Story | Como o MVP atende | Evidência |
|---|---|---|---|
| US-01 | Operador recebe alerta antes de entrar em área de risco | Alerta na tela do operador com nível, scores e **fatores que pesaram**, gerado no POST e persistido em `alertas` | `02-operador-campo.png`, bloco "Decisão registrada" acima |
| US-04 | Gestora vê em mapa o status de risco de cada equipamento | Mapa com pontos por nível + KPIs + tendência por região e por tipo de operação | `01-gestor-frota.png` |
| US-07 | Analista acessa histórico de alertas antes de um sinistro | Histórico auditável de alertas com exportação CSV + trilha de auditoria das decisões | `03-analista-seguradora.png` |

## 5. Como reproduzir

```bash
# 1. ambiente
python -m venv venv && venv/Scripts/activate
pip install -r requirements.txt

# 2. dados (sompo.db não é versionado)
python src/data/pipeline.py
python src/ml/04_predict.py          # predição em lote sobre a base do ETL

# 3. API
python -m uvicorn start_api:app --host 127.0.0.1 --port 8000

# 4. coleta simulada
python src/api/simulador_telemetria.py --n 10 --interval 0 --lote 1

# 5. dashboard (outro terminal)
streamlit run src/dashboard/app.py

# 6. testes
python -m pytest tests/ -q
```

## 6. Limites conhecidos

- `sompo.db` não é versionado: clone limpo exige o passo 2 antes da API (documentado no README).
- As séries do dashboard usam até 1000 registros (teto do `limit` da API).
- Sem `JWT_SECRET_KEY` no `.env`, cada reinício da API invalida os tokens emitidos antes
  (segredo efêmero — decisão registrada em [`seguranca-auditoria.md`](seguranca-auditoria.md)).
