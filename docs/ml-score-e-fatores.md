# Score contínuo e fatores do modelo — Sprint 4 (issue #4)

Correção da lacuna central apontada no feedback da Sprint 3: o score do modelo era um
**valor fixo por classe** e os "fatores principais" eram o **valor absoluto bruto da
variável**, não o quanto ela pesa na predição.

## O que estava errado

| Onde | Comportamento na Sprint 3 |
|------|---------------------------|
| `ml/predictor.py` | `SCORE_POR_NIVEL = {"Baixo": 12, "Médio": 38, "Alto": 63, "Crítico": 88}` — todo registro classificado como "Alto" recebia exatamente 63, com 51% ou 99% de confiança |
| `ml/predictor.py` (`_extrair_top_features`) | Ordenava as variáveis de telemetria pelo **valor absoluto** (`abs(row[coluna])`) e listava as 3 maiores — por isso "distância até a água = 120" aparecia como fator mesmo quando não pesava |
| `api/telemetria_service.py` | Exibia `score_risco` (regra, contínuo) e `score_risco_predito` (modelo, fixo) sem explicar por que o mesmo registro mostrava "81 Crítico" e "63 Alto" (achado B11) |

## Modelo final (retreino da #4)

O `risk_model.pkl` foi retreinado sobre o dataset tratado pelo ETL da #3 (997 registros depois da
higienização) e teve o conjunto de variáveis revisado por cross-validation: **11 features** (saíram
`risco_manutencao` e `indice_desgaste`, combinações de variáveis que já estavam no conjunto — CV
0.8104 contra 0.7974 do conjunto original de 13). Métricas completas em
[`src/ml/relatorio_metricas.md`](../src/ml/relatorio_metricas.md): acurácia 0.8350 no teste,
AUC OvR macro 0.9631, recall de `Crítico` 0.929.

## O que mudou

1. **Score contínuo** (`ml.features.score_continuo`): média das faixas ponderada pelas
   probabilidades do modelo. O representante de cada nível é o **ponto médio da banda** de
   `classificar_risco` (0-25, 26-50, 51-75, 76-100), então o score continua caindo na faixa do
   nível previsto quando esse nível domina — e dois registros "Alto" deixam de empatar.
   `FAIXAS_NIVEL` virou a fonte única das bandas (usada pelo nível e pelo score).
2. **Fatores por contribuição local** (`RiskPredictor._fatores_por_contribuicao`): para cada
   variável, o modelo é reavaliado com ela perturbada (±20% nas contínuas, uma unidade nas
   discretas) e o fator é o quanto a probabilidade do nível previsto muda. Entram as três
   variáveis que mais movem a predição, com corte de 1 ponto percentual — variável que não move
   nada não é listada.
3. **B11 reconciliado**: os dois scores agora são 0-100 contínuos e comparáveis. A API mantém os
   dois nomes porque são duas coisas diferentes (ver abaixo) e o OpenAPI descreve cada um.

### Como ler os dois scores (B11)

| Campo | O que é | Para que serve |
|-------|---------|----------------|
| `score_risco` | Heurística determinística do domínio (`ml.features.score_regra`) | Auditável linha a linha: dá para explicar cada ponto somado |
| `score_risco_predito` | Modelo Random Forest, média das faixas ponderada pelas probabilidades | Captura padrões que a regra não expressa; varia com a confiança do modelo |

Os dois ficam na mesma escala, então a diferença entre eles é informativa: divergência grande
costuma indicar caso ambíguo (o modelo vê risco que a regra não pontua, ou vice-versa).

## Evidências

### Score deixou de ser fixo

Varredura de 8 registros variando manutenção/incidentes sobre a mesma base:

```
níveis e scores: [('Médio', 42), ('Médio', 43), ('Médio', 44), ('Médio', 47),
                  ('Alto', 51), ('Alto', 56), ('Alto', 61), ('Alto', 63)]
scores distintos: 8
```

200 registros da base processada: **56 scores distintos** (o mapa fixo produzia no máximo 4).
Na operação real via API: **14 scores distintos em 19 predições**, cobrindo os 4 níveis.

### Fatores passaram a refletir contribuição

Frequência dos fatores em 200 registros (antes seria ~sempre as 3 variáveis de maior valor):

```
faixa_proximidade_encoded: 177 | umidade_solo_pct: 91 | dias_ultima_manutencao: 59
proximidade_agua_m: 59 | tipo_solo_encoded: 59 | historico_incidentes: 52
velocidade_operacao_kmh: 51 | carga_pct: 27 | precipitacao_mm: 10
declividade_graus: 9 | horas_uso_equipamento: 6
```

O caso que fecha a reclamação do tutor — duas linhas **igualmente longe da água**, com o modelo
listando a proximidade em uma e não na outra (nada de "valor grande = fator"):

```
EQ-GO-0006, 841 m  → score 54 Alto → fatores: historico_incidentes, velocidade_operacao_kmh, umidade_solo_pct
EQ-GO-0006, 2316 m → score 55 Alto → fatores: velocidade_operacao_kmh, dias_ultima_manutencao, proximidade_agua_m
```

Mesmo nível (`Alto`) e scores diferentes nos dois casos — e a proximidade da água só entra onde
realmente muda a decisão. Esse par é o caso de teste `test_fatores_mudam_conforme_o_que_pesa_no_registro`.

### Saída real da API (POST /api/v1/telemetria)

```
EQ-GO-0006 -> 81 (Crítico) | predito 55 (Alto)    | alerta SIM
EQ-PR-0025 -> 58 (Alto)    | predito 33 (Médio)   | alerta NÃO
EQ-GO-0007 -> 100 (Crítico)| predito 81 (Crítico) | alerta SIM
EQ-RS-0039 -> 77 (Crítico) | predito 18 (Baixo)   | alerta NÃO
```

Persistido em `scores_modelo`, com `fatores_principais` por registro:

```
#1016 regra= 77 Crítico | modelo= 18 Baixo   fatores=['faixa_proximidade_encoded', 'umidade_solo_pct', 'historico_incidentes']
#1015 regra= 65 Alto    | modelo= 60 Alto    fatores=['faixa_proximidade_encoded', 'proximidade_agua_m', 'velocidade_operacao_kmh']
#1013 regra=100 Crítico | modelo= 81 Crítico fatores=['velocidade_operacao_kmh', 'umidade_solo_pct', 'faixa_proximidade_encoded']
```

O caso `#1016` mostra o valor de manter os dois scores: a regra pontua 77 (Crítico) e o modelo
18 (Baixo) — divergência grande sinaliza caso ambíguo, que é exatamente o que o operador precisa
inspecionar antes de confiar no alerta.

### Regressão automatizada

`tests/test_unit.py`: score contínuo ponderado, representante dentro da própria faixa, fatores
por contribuição (incluindo o caso das duas linhas longe da água) e continuidade do score.
Cobertura total: **49 testes passando**. `src/ml/train_model.py` reproduz o treino, a avaliação e a
reescrita do relatório de métricas.

### Propagação: alerta e dashboard

O nível predito e os fatores chegam aos dois pontos onde a decisão acontece:

```
POST /api/v1/telemetria (Crítico)
recomendacao: 🚨 Risco crítico detectado. Suspender a operação imediatamente e acionar o gestor
              de frota. Fatores principais: tipo de solo, dias desde última manutenção, percentual de carga.

alertas (banco):
id_alerta 13 | nivel_risco Crítico | score_risco 88 | mensagem = a mesma recomendação acima
```

Na visão do operador (verificada rodando o dashboard contra a API real):

```
Score da regra = 100        |  Score do modelo (Crítico) = 88   (delta -12 vs regra)
Variáveis que mais pesaram na predição do modelo: `tipo_solo_encoded`, `dias_ultima_manutencao`, `carga_pct`
ALERTA CRÍTICO para EQ-MT-0023: risco crítico (score da regra 100, score do modelo 88).
Fatores que pesaram: tipo_solo_encoded, dias_ultima_manutencao, carga_pct. [...]
```

O texto do alerta no dashboard citava **sempre** "proximidade de água e umidade do solo", mesmo
quando nenhuma das duas pesava — mesma classe de problema do feedback. Agora cita os fatores do
registro. O `GET /api/v1/telemetria` também passou a devolver `fatores_principais`, que é o que
alimenta essa linha.

### Regressão encontrada ao validar o dashboard

O dashboard pedia `limit=2000` em `GET /api/v1/telemetria`; a validação de `limit` (1-1000)
introduzida na issue #2 devolvia **422** — a tela abria com "Erro ao carregar telemetria" e era um
bug ativo desde a #2, sem teste que pegasse. Corrigido para o teto aceito
(`LIMITE_HISTORICO = 1000`) e coberto por `test_telemetria_limit_no_teto_do_dashboard`.

## Limitações declaradas

- A atribuição é **sensibilidade local** (uma variável por vez, no próprio registro) — não é
  SHAP. Responde "quanto mexer nesta variável muda a predição", não "qual a contribuição exata
  dentro da árvore".
- Quando duas classes ficam praticamente empatadas em torno de uma fronteira de faixa, o score
  contínuo pode indicar a faixa vizinha do nível previsto por `argmax`. É esperado: o nível é a
  classe do modelo e o score é a média ponderada — as `probabilidades` ficam expostas na
  resposta para inspecionar o empate.
- Magnitudes (em pontos percentuais) são calculadas e usadas para ordenar, mas hoje só os nomes
  das variáveis são expostos na API/dashboard; expor o valor é candidato natural para a #7.
