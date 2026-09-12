"""Pacote de engenharia de dados (ETL) do AgroRisk AI.

Módulos:
- ``generate_dataset``: gera o dataset simulado determinístico (SEED=42).
- ``feature_engineering``: features de risco + validação + artefatos (scaler/encoders).
- ``load_to_sql``: carga do CSV processado no banco SQLite.
- ``pipeline``: orquestra schema → dataset → features → carga.
"""