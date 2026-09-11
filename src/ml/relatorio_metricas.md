# Relatório de Métricas — Issue #3
**Modelo escolhido:** Random Forest  
**Acurácia (CV k=5):** 0.7737  
**Acurácia (teste):** 0.8400  
**F1 Macro (teste):** 0.8432  

## Métricas por Classe

| Classe | Precision | Recall | F1-Score |
|--------|-----------|--------|----------|
| Alto | 0.7736 | 0.8039 | 0.7885 |
| Baixo | 0.9375 | 0.8654 | 0.9000 |
| Crítico | 0.8810 | 0.8810 | 0.8810 |
| Médio | 0.7895 | 0.8182 | 0.8036 |

## Comparação com Baseline

| Métrica | Baseline | Modelo |
|---------|----------|--------|
| Acurácia | 0.4900 | 0.8400 |
| F1 Macro | 0.4533 | 0.8432 |

## Imagens

- ![Matriz de Confusão](../../assets/ml_matriz_confusao.png)
- ![Métricas por Classe](../../assets/ml_metricas_por_classe.png)
- ![Feature Importance](../../assets/ml_feature_importance.png)
