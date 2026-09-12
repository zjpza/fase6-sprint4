"""Testes das funções puras de features e score (fonte única: ml.features)."""
from __future__ import annotations

import pandas as pd
import pytest

from ml.features import (
    calcular_features as _calcular_features,
    classificar_risco as _classificar_risco,
    faixa_proximidade as _faixa_proximidade,
    score_regra as _score_regra,
)


def test_faixa_proximidade():
    assert _faixa_proximidade(10) == "Crítico"
    assert _faixa_proximidade(49) == "Crítico"
    assert _faixa_proximidade(50) == "Alto"
    assert _faixa_proximidade(199) == "Alto"
    assert _faixa_proximidade(200) == "Médio"
    assert _faixa_proximidade(499) == "Médio"
    assert _faixa_proximidade(500) == "Baixo"


def test_classificar_risco():
    assert _classificar_risco(0) == "Baixo"
    assert _classificar_risco(25) == "Baixo"
    assert _classificar_risco(26) == "Médio"
    assert _classificar_risco(50) == "Médio"
    assert _classificar_risco(51) == "Alto"
    assert _classificar_risco(75) == "Alto"
    assert _classificar_risco(76) == "Crítico"
    assert _classificar_risco(100) == "Crítico"


def _payload_alto():
    return {
        "proximidade_agua_m": 30,
        "umidade_solo_pct": 90,
        "precipitacao_mm": 50,
        "tipo_solo": "Argiloso",
        "declividade_graus": 15,
        "velocidade_operacao_kmh": 10,
        "carga_pct": 95,
        "historico_incidentes": 3,
        "dias_ultima_manutencao": 60,
        "horas_uso_equipamento": 5000,
        "visibilidade_m": 200,
        "tipo_operacao": "Campo",
    }


def test_score_regra_basico():
    row = _calcular_features(_payload_alto())
    score = _score_regra(row)
    assert 0 <= score <= 100
    assert score >= 70


def test_score_regra_baixo():
    payload = {
        "proximidade_agua_m": 800,
        "umidade_solo_pct": 20,
        "precipitacao_mm": 0,
        "tipo_solo": "Arenoso",
        "declividade_graus": 2,
        "velocidade_operacao_kmh": 5,
        "carga_pct": 30,
        "historico_incidentes": 0,
        "dias_ultima_manutencao": 5,
        "horas_uso_equipamento": 500,
        "visibilidade_m": 5000,
        "tipo_operacao": "Transporte",
    }
    row = _calcular_features(payload)
    score = _score_regra(row)
    assert 0 <= score <= 100
    assert score <= 25


def test_calcular_features_campos():
    row = _calcular_features(_payload_alto())
    for chave in (
        "tipo_solo_encoded",
        "tipo_operacao_encoded",
        "faixa_proximidade_agua",
        "faixa_proximidade_encoded",
        "indice_desgaste",
        "risco_solo",
        "risco_atolamento",
        "risco_operacional",
        "risco_manutencao",
    ):
        assert chave in row


# --- Sprint 4 (#2 REFACT): correções da auditoria (B3, B4, validações) ---

def test_normalizar_base_url_simulador():
    """B3: --base-url sem /api/v1 não pode mais gerar 404 no simulador."""
    from api.simulador_telemetria import _normalizar_base_url

    assert _normalizar_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000/api/v1"
    assert _normalizar_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/api/v1"
    assert _normalizar_base_url("http://127.0.0.1:8000/api/v1") == "http://127.0.0.1:8000/api/v1"
    assert _normalizar_base_url("http://127.0.0.1:8000/api/v1/") == "http://127.0.0.1:8000/api/v1"


def test_pipeline_importavel_como_pacote():
    """B4: ETL deve importar como pacote a partir de src/, sem depender de cwd=src/data."""
    import data.pipeline as pipeline

    assert callable(pipeline.executar_schema)
    assert callable(pipeline.run_pipeline)


def test_validar_features_mensagem_de_erro_clara():
    """Validação de features deve levantar ValueError com o problema nomeado, não assert genérico."""
    from data.feature_engineering import validar_features

    df = pd.DataFrame({"score_risco": [150], "diff_score": [0]})
    with pytest.raises(ValueError, match="score_risco"):
        validar_features(df)