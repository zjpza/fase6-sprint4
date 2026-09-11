# src/data
Dados brutos e processados do projeto AgroRisk AI.

## Objetivo

Esta pasta contém o pipeline de ETL (Extração, Transformação e Carga) que processa os dados de sensores e telemetria para alimentar o banco SQL e os modelos de ML.

## Estrutura

- `raw/`: dados simulados dos sensores (CSV). Baseado no dataset da Sprint 1, expandido com mais registros e variedade de cenários (baixo, médio, alto e crítico risco).
- `processed/`: dados após engenharia de features (CSV normalizado), prontos para ingestão SQL.

## Scripts (a implementar na Sprint 2)

- `generate_dataset.py`: gera dataset simulado expandido a partir das variáveis definidas na Sprint 1 (proximidade de água, umidade do solo, declividade, condições climáticas, histórico de uso).
- `feature_engineering.py`: cria features de risco (ex: `_risk_proximity`, `_risk_soil`, `_risk_weather`), normaliza variáveis numéricas e codifica categóricas (tipo_solo, tipo_equipamento).
- `load_to_sql.py`: carrega dados processados no banco SQLite/MySQL usando SQLAlchemy.

## Variáveis do Dataset (mantidas da Sprint 1)

| Variável | Descrição |
|----------|-----------|
| `proximidade_agua_m` | Distância de rios/lagos. Faixas de risco: >500m=baixo, 200-500=médio, 50-200=alto, <50=crítico |
| `umidade_solo_pct` | Umidade do solo. Valores altos em solos argilosos elevam risco de atolamento |
| `precipitacao_mm` | Chuva nas últimas 24h. Acima de 50mm + solo argiloso = risco crítico |
| `declividade_graus` | Inclinação do terreno. Acima de 15° aumenta risco de tombamento |
| `velocidade_operacao_kmh` | Velocidade atual. Excesso de velocidade em carga aumenta risco |
| `carga_pct` | % de capacidade de carga. Acima de 90% + solo molhado = risco alto |
| `historico_incidentes` | Incidentes nos últimos 12 meses. Histórico elevado indica padrão de risco |
| `dias_ultima_manutencao` | Tempo sem manutenção. Acima de 60 dias eleva risco mecânico |
| `horas_uso_equipamento` | Horas totais. Desgaste acumulado aumenta probabilidade de falha |

## Saídas

Os scripts devem gerar:
- `raw/dataset_simulado.csv` — dados brutos com ~1000+ registros
- `processed/features.csv` — dados com features de risco calculadas e normalizadas
