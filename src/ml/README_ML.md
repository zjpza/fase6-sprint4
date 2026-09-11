# ML — Predição de Risco Operacional

Módulo de Machine Learning para classificação de nível de risco de equipamentos agrícolas.

## Stack e Versões

| Biblioteca     | Versão recomendada | Uso                          |
|----------------|--------------------|------------------------------|
| pandas         | ≥ 1.5              | Manipulação de dados         |
| scikit-learn   | ≥ 1.2              | Modelos, métricas, split     |
| xgboost        | ≥ 1.7 (opcional)   | XGBoost Classifier           |
| matplotlib     | ≥ 3.6              | Gráficos                     |
| seaborn        | ≥ 0.12             | Visualizações estatísticas   |
| numpy          | ≥ 1.23             | Operações numéricas          |

## Estrutura de arquivos

```
src/ml/
├── 01_eda.ipynb           # Análise exploratória
├── 02_modelagem.ipynb     # Treinamento e cross-validation
├── 03_avaliacao.ipynb     # Métricas e feature importance
├── 04_predict.py          # Script de predição e integração com banco
├── relatorio_metricas.md  # Gerado pelo 03_avaliacao.ipynb
├── README_ML.md           # Este arquivo
└── models/
    └── risk_model.pkl     # Modelo treinado (gerado pelo 02_modelagem.ipynb)
```

## Pré-requisitos

```bash
pip install pandas scikit-learn matplotlib seaborn xgboost notebook
```

## Como executar (na ordem correta)

### 1. EDA
```bash
jupyter notebook src/ml/01_eda.ipynb
```

### 2. Treinamento
```bash
jupyter notebook src/ml/02_modelagem.ipynb
```
→ Salva `src/ml/models/risk_model.pkl`

### 3. Avaliação
```bash
jupyter notebook src/ml/03_avaliacao.ipynb
```
→ Gera `src/ml/relatorio_metricas.md` e imagens em `/assets/`

### 4. Predição (linha de comando)
```bash
# Predição em lote (todos os equipamentos do banco)
python src/ml/04_predict.py

# Predição para um equipamento específico
python src/ml/04_predict.py --equipamento_id EQ001
```

## Target e Classes

| Classe   | Faixa de `score_risco` (0–100) |
|----------|--------------------------------|
| Baixo    | 0 – 25                         |
| Médio    | 26 – 50                        |
| Alto     | 51 – 75                        |
| Crítico  | 76 – 100                       |

> **Nota:** A variável `nivel_risco` já existe no banco `sompo.db`, calculada pela fórmula da Issue #1 que combina proximidade d'água, umidade/tipo de solo, declividade, clima, uso e histórico de incidentes — e não apenas a distância da água. O modelo aprende a reproduzir essa classificação a partir das variáveis de sensores (sem usar o `score_risco` como entrada, para evitar *data leakage*).

## Features utilizadas

| Feature                  | Tipo     | Descrição                                  |
|--------------------------|----------|--------------------------------------------|
| proximidade_agua_m       | float    | Distância até corpo d'água (metros)        |
| precipitacao_mm          | float    | Precipitação registrada                    |
| umidade_solo_pct         | float    | Umidade do solo (%)                        |
| declividade_graus        | float    | Declividade do terreno                     |
| horas_uso_equipamento    | int      | Horas de uso no dia                        |
| dias_ultima_manutencao   | int      | Dias desde última manutenção               |
| velocidade_operacao_kmh  | float    | Velocidade média de operação               |
| carga_pct                | float    | Carga do equipamento (%)                   |
| historico_incidentes     | int      | Número de incidentes anteriores            |
| risco_manutencao         | int      | Score de risco de manutenção               |
| indice_desgaste          | float    | Índice de desgaste (0 a 1)                 |
| tipo_solo_encoded        | int      | Tipo de solo codificado                    |
| faixa_proximidade_encoded| int      | Faixa de proximidade codificada            |

> **Decisão técnica — exclusão de `score_risco`:** o target `nivel_risco` é a faixa do `score_risco`. Usar `score_risco` (ou `score_risco_calculado`, `diff_score`) como feature seria *data leakage* — o modelo decoraria o gabarito e atingiria 100% artificial, sem comprovar eficácia. O modelo é treinado apenas a partir de variáveis de sensores e features derivadas delas, demonstrando que aprende o padrão de risco a partir da telemetria — exatamente o caso de uso real onde a fórmula fixa não existe.

## Resultados

Ver `relatorio_metricas.md` para resultados completos após rodar os notebooks.

Imagens geradas em `/assets/`:
- `ml_comparacao_modelos.png` — comparação CV
- `ml_matriz_confusao.png` — matriz de confusão
- `ml_metricas_por_classe.png` — F1/Precision/Recall
- `ml_feature_importance.png` — importância das features
- `ml_baseline_vs_modelo.png` — modelo vs baseline
