"""Pacote de engenharia de dados (ETL) do AgroRisk AI.

Módulos:
- ``generate_dataset``: gera o dataset simulado determinístico (SEED=42).
- ``feature_engineering``: features de risco + validação + artefatos (scaler/encoders).
- ``validacao_dados``: higieniza a telemetria (faltantes, duplicidades, domínios e faixas).
- ``conexao``: conexão SQLite compartilhada (foreign keys + espera por lock).
- ``load_to_sql``: carga idempotente do CSV processado, com rastreabilidade até a fonte.
- ``pipeline``: orquestra schema → dataset → features → carga.
"""
