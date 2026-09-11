# src/ml
Modelos preditivos e avaliação estatística do projeto AgroRisk AI.

## Objetivo

Desenvolver, treinar e validar modelos de Machine Learning capazes de classificar o nível de risco operacional (Baixo / Médio / Alto / Crítico) e gerar scores contínuos (0–100) para apoiar as User Stories US-01 (alerta ao operador), US-04 (dashboard do gestor) e US-07 (auditoria do analista).

## Notebooks e Scripts (a implementar na Sprint 2)

- `01_eda.ipynb`: Análise Exploratória de Dados (EDA). Correlações entre variáveis, distribuição de risco por tipo de equipamento/solo/região, identificação de outliers.
- `02_modelagem.ipynb`: Treinamento de modelos ML. Comparação entre Random Forest e XGBoost, otimização de hiperparâmetros (GridSearch), treinamento com validação cruzada.
- `03_avaliacao.ipynb`: Métricas estatísticas. Matriz de confusão, F1-score macro e por classe, AUC-ROC, RMSE/MAE para score de risco, curva ROC, feature importance.
- `04_predict.py`: Script de predição para novos dados. Recebe entrada de telemetria, carrega modelo salvo e retorna score, nível e alerta.
- `models/`: Modelos serializados (.pkl) após treinamento.
- `README_ML.md`: Resumo dos algoritmos, hiperparâmetros e métricas finais.

## Algoritmos e Abordagem

**Abordagem híbrida:**
1. **Regressão** — prediz `score_risco` contínuo (0–100)
2. **Classificação** — prediz `nivel_risco` em 4 classes (Baixo/Médio/Alto/Crítico)

**Algoritmos escolhidos:**
- **Random Forest**: robusto a dados faltantes, excelente interpretabilidade via feature importance, bom baseline.
- **XGBoost**: alto desempenho, eficiente com datasets tabulares, boa generalização.

**Por que esses algoritmos:**
- Lidam com variáveis mistas (numéricas + categóricas como tipo_solo, tipo_equipamento).
- Robustos a dados faltantes, comuns em sensores IoT rurais.
- Permitem explicar ao operador/gestor quais fatores mais contribuíram para o alerta (interpretabilidade).

## Métricas de Avaliação

| Métrica | Meta Esperada | Justificativa |
|---------|--------------|---------------|
| Recall (Alto/Crítico) | ≥ 0.85 | Evitar sinistro não previsto (falso negativo custa muito) |
| F1-score (macro) | ≥ 0.75 | Equilíbrio entre precisão e recall em todas as classes |
| RMSE (score) | ≤ 10 | Score de risco preciso para decisões operacionais |
| AUC-ROC | ≥ 0.85 | Bom separador entre emitir/não emitir alerta |
| Acurácia geral | ≥ 0.80 | Modelo consistentemente correto |

## Variáveis de Entrada (features)

```
precipitacao_mm, umidade_solo_pct, tipo_solo_encoded, proximidade_agua_m,
declividade_graus, horas_uso_equipamento, dias_ultima_manutencao,
velocidade_operacao_kmh, carga_pct, historico_incidentes,
temperatura_c, velocidade_vento_kmh
```

## Saída Esperada

```python
{
    'score_risco': 74,           # 0–100
    'nivel_risco': 'Alto',       # Baixo / Médio / Alto / Crítico
    'alerta': True,
    'recomendacao': 'Solo saturado e proximidade de corpo dagua detectados. Recomenda-se suspender a operacao e aguardar 48h.',
    'fatores_principais': ['umidade_solo_pct', 'proximidade_agua_m', 'precipitacao_mm']
}
```
