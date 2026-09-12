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
| **Quem decide o alerta** | A regra (fonte única, auditável) — o modelo é segunda opinião; divergência sinaliza caso ambíguo | evita alerta na tela sem registro na trilha (e vice-versa) |

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
EQ-GO-0006 -> 81 (Crítico) | predito 55 (Alto)    | alerta SIM | divergente
EQ-PR-0025 -> 58 (Alto)    | predito 33 (Médio)   | alerta SIM | divergente
EQ-GO-0007 -> 100 (Crítico)| predito 81 (Crítico) | alerta SIM
EQ-RS-0039 -> 77 (Crítico) | predito 18 (Baixo)   | alerta SIM | divergente
```

O `alerta` é a decisão da **regra** (fonte única) e `divergente` sinaliza que regra e modelo
classificam em níveis diferentes. Na Sprint 3, `EQ-PR-0025` e `EQ-RS-0039` mostravam
`alerta NÃO` — o modelo (Médio/Baixo) decidia, a regra gritava Alto/Crítico na tela e o alerta
**nunca entrava** no histórico auditável. Agora o alerta segue a regra e a divergência fica
explícita para o operador.

Persistido em `scores_modelo`, com `fatores_principais` por registro:

```
#1003 regra= 77 Crítico | modelo= 18 Baixo   fatores=['faixa_proximidade_encoded', 'umidade_solo_pct', 'historico_incidentes']
#1002 regra= 65 Alto    | modelo= 60 Alto    fatores=['faixa_proximidade_encoded', 'proximidade_agua_m', 'velocidade_operacao_kmh']
#1000 regra=100 Crítico | modelo= 81 Crítico  fatores=['velocidade_operacao_kmh', 'umidade_solo_pct', 'faixa_proximidade_encoded']
```

O caso `#1003` mostra o valor de manter os dois scores: a regra pontua 77 (Crítico) e o modelo
18 (Baixo) — o alerta foi emitido pela regra e a divergência sinaliza caso ambíguo, que é
exatamente o que o operador precisa inspecionar antes de confiar.

### Regressão automatizada

`tests/test_unit.py`: score contínuo ponderado, representante dentro da própria faixa, fatores
por contribuição (incluindo o caso das duas linhas longe da água) e continuidade do score.
Cobertura total: **80 testes passando**. `src/ml/train_model.py` reproduz o treino, a avaliação e a
reescreta do relatório de métricas.

### Propagação: alerta e dashboard

A **regra** decide o alerta (fonte única) e a mensagem cita as penalidades que somaram o score;
o modelo entra como segunda opinião, e a divergência entre os dois é sinalizada em todas as
superfícies (resposta da API, `alertas`, trilha de auditoria e tela do operador):

```
POST /api/v1/telemetria (EQ-MT-0023, regra Crítico, modelo Crítico — convergente)
recomendacao: 🚨 Risco crítico detectado. Suspender a operação imediatamente e acionar o gestor
              de frota. Fatores principais: proximidade de água (47 pts), umidade do solo (22 pts), declividade (22 pts).
divergente: false

alertas (banco, EQ-PR-0025 — regra Alto × modelo Médio):
id_alerta 2 | nivel_risco Alto | score_risco 58 | Preventivo |
  ⚠️ Risco alto. Reduzir velocidade, evitar áreas alagadiças e monitorar condições do solo.
  Fatores principais: declividade (16 pts), velocidade de operação (11 pts), umidade do solo (9 pts).
  Segunda opinião do modelo: Médio (33) — caso divergente, inspecione as condições antes de confiar.
```

Na visão do operador (verificada rodando o dashboard contra a API real — captura em
`assets/prints/02-operador-campo.png`):

```
Score da regra = 58          |  Score do modelo (Médio) = 33   (delta -25 vs regra)
Variáveis que mais pesaram na predição do modelo: `velocidade_operacao_kmh`, `faixa_proximidade_encoded`, `historico_incidentes`
🚨 ALERTA ALTO para EQ-MT-0023: ⚠️ Risco alto. Reduzir velocidade, evitar áreas alagadiças e
  monitorar condições do solo. Fatores principais: declividade (16 pts), velocidade de
  operação (11 pts), umidade do solo (9 pts). Segunda opinião do modelo: Médio (33) — caso
  divergente, inspecione as condições antes de confiar.
```

O texto do alerta cita as **penalidades nomeadas da regra** com os pontos de cada uma
(`ml.features.componentes_regra`), não uma causa fixa — na Sprint 3 ele dizia sempre
"proximidade de água e umidade do solo", mesmo quando nenhuma das duas pesava. A divergência
aparece na própria mensagem ("Segunda opinião do modelo") e o caption acima continua
rotulando os fatores do modelo como o que são: segunda opinião.

### Regressão encontrada ao validar o dashboard

O dashboard pedia `limit=2000` em `GET /api/v1/telemetria`; a validação de `limit` (1-1000)
introduzida na issue #2 devolvia **422** — a tela abria com "Erro ao carregar telemetria" e era um
bug ativo desde a #2, sem teste que pegasse. Corrigido para o teto aceito
(`LIMITE_HISTORICO = 1000`) e coberto por `test_telemetria_limit_no_teto_do_dashboard`.

## Limitação estrutural: o rótulo vem da regra

O rótulo de treino (`nivel_risco`) não é um desfecho observado — ele deriva de `score_risco`,
heurística determinística calculada sobre as **próprias variáveis de entrada**. O modelo é,
portanto, um substituto suavizado da regra: aprende a função que gerou os rótulos e as métricas
de [`relatorio_metricas.md`](../src/ml/relatorio_metricas.md) medem quão bem ele **recupera a
regra**, não uma estimativa independente de risco real. Essa circularidade é confrontada em vez
de escondida: "qual valor o ML agrega sobre a regra que o gerou?" — nesta base, o valor do modelo
é **score contínuo + explicação local + detector de ambiguidade**, não acurácia sobre risco real.

Números reais sobre a base processada (997 registros, predição do `RiskPredictor` em lote):

```
distribuição de nivel_risco (regra) : {'Médio': 0.274, 'Baixo': 0.259, 'Alto': 0.256, 'Crítico': 0.211}
divergência regra × modelo          : 3.4% dos registros em níveis diferentes
Alto/Crítico pela regra              : 46.7% da base
```

Leitura honesta: a divergência de 3,4% é o sinal que o modelo agrega na prática — casos em que
a suavização das probabilidades cai em banda diferente da soma determinística de penalidades.
É esse detector de ambiguidade (campo `divergente` na API), junto com o score contínuo e os
fatores locais, que justifica manter o modelo na pilha **como segunda opinião**; a decisão de
alerta fica com a regra, auditável ponto a ponto. Em produção com dados da Sompo, o alvo deve ser
desfecho observado (sinistro, near-miss, manutenção corretiva); o pipeline
(`train_model.py` sobre a saída do ETL) já aceita esse troco de rótulo sem mudança estrutural.

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
