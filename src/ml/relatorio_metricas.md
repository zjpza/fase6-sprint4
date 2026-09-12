# Relatório de Métricas — Sprint 4 (issue #4)

Modelo final retreinado sobre o dataset tratado pelo ETL refinado da #3
(`data/processed/features.csv`, 997 registros) — 797 para treino e
200 para teste, split estratificado 80/20 com `random_state=42`.

**Modelo escolhido:** Random Forest (`n_estimators=200`, `min_samples_split=5`) — mesma família da
Sprint 2, mantida para dar continuidade à comparação de métricas entre sprints.

## Resumo

| Métrica | Baseline (só distância até a água) | Modelo |
|---|---|---|
| Acurácia (teste) | 0.4800 | **0.8350** |
| AUC (OvR macro) | — | **0.9631** |
| F1 macro | — | **0.8398** |
| Acurácia CV (k=5) | — | 0.8104 ± 0.0130 |

## Métricas por classe

| Classe | Precision | Recall | F1 | Registros |
|--------|-----------|--------|----|-----------|
| Alto | 0.830 | 0.765 | 0.796 | 51 |
| Baixo | 0.882 | 0.865 | 0.874 | 52 |
| Crítico | 0.907 | 0.929 | 0.918 | 42 |
| Médio | 0.746 | 0.800 | 0.772 | 55 |
| **macro avg** | 0.841 | 0.840 | 0.840 | 200 |

O **recall de `Crítico` e `Alto`** é a métrica que mais importa no problema: deixar passar um
equipamento que o modelo consideraria perigoso custa mais caro (sinistro) do que um alerta
preventivo a mais. `AUC` (OvR macro) entra como medida de separabilidade que não depende do corte
escolhido — útil porque as quatro classes são ordinais e a fronteira entre "Alto" e "Crítico" é
sensível ao limiar.

## Matriz de confusão (teste)

| Real \ Previsto | Alto | Baixo | Crítico | Médio |
|---|---|---|---|---|
| Alto | 39 | 0 | 4 | 8 |
| Baixo | 0 | 45 | 0 | 7 |
| Crítico | 3 | 0 | 39 | 0 |
| Médio | 5 | 6 | 0 | 44 |

## Revisão das variáveis

Conjuntos avaliados por cross-validation antes de fixar as features do modelo final:

| Conjunto de features | Nº | Acurácia CV (k=5) |
|---|---|---|
| sem os dois derivados ✅ escolhido | 11 | 0.8104 ± 0.0130 |
| sem risco_manutencao | 12 | 0.8014 ± 0.0133 |
| sem risco_manutencao e sem faixa | 11 | 0.8004 ± 0.0129 |
| Sprint 2 (13 features) | 13 | 0.7974 ± 0.0207 |
| sem indice_desgaste | 12 | 0.7954 ± 0.0109 |
| sem faixa_proximidade_encoded | 12 | 0.7873 ± 0.0264 |

**Escolhido:** sem os dois derivados (11 features) — `proximidade_agua_m`, `precipitacao_mm`, `umidade_solo_pct`, `declividade_graus`, `horas_uso_equipamento`, `dias_ultima_manutencao`, `velocidade_operacao_kmh`, `carga_pct`, `historico_incidentes`, `tipo_solo_encoded`, `faixa_proximidade_encoded`.

Importância no modelo final (impureza das árvores e queda de acurácia ao permutar cada variável
no conjunto de teste):

| Variável | Importância (árvores) | Queda de acurácia ao permutar |
|---|---|---|
| proximidade_agua_m | 0.2054 | +0.1595 |
| velocidade_operacao_kmh | 0.1513 | +0.1275 |
| umidade_solo_pct | 0.1230 | +0.1455 |
| faixa_proximidade_encoded | 0.1161 | +0.1450 |
| dias_ultima_manutencao | 0.1127 | +0.1500 |
| precipitacao_mm | 0.0761 | +0.0405 |
| historico_incidentes | 0.0559 | +0.0640 |
| declividade_graus | 0.0497 | +0.0125 |
| horas_uso_equipamento | 0.0456 | +0.0110 |
| carga_pct | 0.0454 | +0.0085 |
| tipo_solo_encoded | 0.0189 | +0.0070 |

## Decisões

- **`score_risco` e `score_risco_calculado` não entram como features**: o rótulo (`nivel_risco`)
  deriva deles — usá-los seria vazamento de target, inflando a acurácia sem valor preditivo real.
- **`fatores` e features derivadas**: `risco_manutencao` e `indice_desgaste` são combinações de
  variáveis que já estão no conjunto; a decisão de mantê-las ou cortá-las foi tomada pelos
  números acima (CV), não por intuição.
- **Fatores exibidos na API** não saem desta importância global: cada predição calcula a
  contribuição local das variáveis (ver `docs/ml-score-e-fatores.md`).
- **Limitação estrutural — o rótulo vem da própria regra**: `nivel_risco` deriva de
  `score_risco`, heurística determinística sobre as próprias variáveis de entrada. As
  métricas acima medem quão bem o modelo **recupera a regra** (substituto suavizado com score
  contínuo, fatores locais e sinal de ambiguidade) — não uma estimativa independente de
  risco real. Em produção com dados da Sompo, o alvo deve ser desfecho observado (sinistro,
  near-miss, manutenção corretiva); o pipeline (`train_model.py` sobre a saída do ETL) já
  aceita esse troco de rótulo sem mudança estrutural.
