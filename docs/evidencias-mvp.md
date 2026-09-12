# Evidências do MVP — Sprint 4 (issue #8)

Prova de que o MVP integrado funciona ponta a ponta: entrada de telemetria → banco → modelo →
score → alerta/relatório → auditoria, com a suite verde e as leituras de volta pela API.

## 1. Suite de testes

```
python -m pytest tests/ -q
76 passed, 2 warnings in 27.37s
```

| Arquivo | Casos | Cobre |
|---|---|---|
| `tests/test_unit.py` | 20 | Funções puras de feature/score, score contínuo, fatores por contribuição, retry/retomada do simulador |
| `tests/test_api.py` | 36 | Login, RBAC, POST/GET telemetria, 409 de coleta repetida, payloads sujos, token expirado/forjado, auditoria |
| `tests/test_etl.py` | 15 | Idempotência da carga, higienização por motivo, rastreabilidade, migração de base legada |
| `tests/test_e2e.py` | 3 | **Fluxo completo**: ETL em diretório temporário → API contra esse banco → score → alerta → auditoria |
| `tests/conftest.py` | — | Banco temporário por teste, `TestClient`, segredo de teste fixo |

As 2 warnings restantes vêm de bibliotecas (depreciações do Starlette/anyio), não do projeto —
eram **65** antes desta sprint.

## 2. Execução demonstrativa de ponta a ponta

### Estado antes da coleta

```
telemetria          : 1045
  por fonte         : {'api': 48, 'dataset_simulado': 997}
scores_modelo       : 1045
alertas             : 26
eventos de auditoria: 146
entradas sem score  : 0
```

### Coleta simulada (lote novo, 10 registros, sem intervalo)

```
python src/api/simulador_telemetria.py --n 10 --interval 0 --lote 3
EQ-BA-0035 -> 52 (Alto) | predito 14 (Baixo) | alerta NÃO
Resumo: 10 enviados | 10 aceitos | 0 já registrados | 0 rejeitados pela API | 0 falhas de rede
```

### Estado depois da coleta

```
telemetria          : 1055 (antes 1045)      ← +10 exatos
scores_modelo       : 1055 (antes 1045)
alertas             : 30 (antes 26)
eventos de auditoria: 167 (antes 146)
coletas do lote 3   : 10
entradas sem score  : 0                       ← toda entrada tem score
duplicados equip+inst: 0
integridade         : ok
```

### Decisão registrada pela trilha

```
2026-09-12T05:32:05 | decisao_risco |
  score_regra=52 nivel_regra=Alto score_modelo=14 nivel_modelo=Baixo alerta=0
  fatores=faixa_proximidade_encoded,horas_uso_equipamento,proximidade_agua_m
```

### Alerta emitido (com os fatores do registro)

```
Alto | score 70 | Preventivo |
⚠️ Risco alto. Reduzir velocidade, evitar áreas alagadiças e monitorar condições do solo.
Fatores principais: velocidade de operação, [...]
```

### Leituras de volta pela API (gestor e analista autenticados)

```
GET /resumo-frota            : 200 — 46 equipamentos
GET /equipamentos            : 50 equipamentos
GET /telemetria?limit=1      : regra 52 Alto | modelo 14 Baixo | fatores ['faixa_proximidade_encoded', 'horas_uso_equipamento', 'proximidade_agua_m']
GET /alertas                 : 30 alertas
GET /equipamentos/EQ-MT-0023/risco : 200 — regra Alto × modelo Médio
GET /auditoria?limit=3       : 3 eventos (último: login de Ricardo Mendes)
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
