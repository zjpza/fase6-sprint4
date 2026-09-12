"""Fluxo completo da solução: ETL → banco → API → modelo → alerta → auditoria.

Roda o pipeline de verdade em caminhos temporários e exercita a API contra o banco
gerado por ele — é a prova de ponta a ponta do MVP (issue #8), sem depender do
banco de demonstração nem de servidor no ar.
"""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest


@pytest.fixture
def ambiente_e2e(tmp_path, monkeypatch):
    """Pipeline completo em diretórios temporários, com todas as rotas de arquivo redirecionadas."""
    from data import feature_engineering, generate_dataset, load_to_sql, pipeline

    data_dir = tmp_path / "data"
    monkeypatch.setattr(generate_dataset, "OUTPUT_PATH", data_dir / "raw" / "dataset_simulado.csv")
    monkeypatch.setattr(feature_engineering, "RAW_PATH", data_dir / "raw" / "dataset_simulado.csv")
    monkeypatch.setattr(feature_engineering, "OUTPUT_PATH", data_dir / "processed" / "features.csv")
    monkeypatch.setattr(feature_engineering, "SCALER_PATH", data_dir / "scaler.pkl")
    monkeypatch.setattr(feature_engineering, "ENCODERS_PATH", data_dir / "label_encoders.pkl")
    monkeypatch.setattr(pipeline, "RAW_OUTPUT", data_dir / "raw" / "dataset_simulado.csv")
    monkeypatch.setattr(pipeline, "OUTPUT_PATH", data_dir / "processed" / "features.csv")
    monkeypatch.setattr(pipeline, "RAW_PATH", data_dir / "raw" / "dataset_simulado.csv")
    monkeypatch.setattr(pipeline, "DB_PATH", tmp_path / "e2e.db")
    monkeypatch.setattr(load_to_sql, "DB_PATH", tmp_path / "e2e.db")
    monkeypatch.setattr(load_to_sql, "FEATURES_PATH", data_dir / "processed" / "features.csv")

    pipeline.run_pipeline(n_registros=500)

    conn = sqlite3.connect(tmp_path / "e2e.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    yield tmp_path / "e2e.db", conn
    conn.close()


def test_fluxo_completo_etl_api_alerta_auditoria(ambiente_e2e):
    """ETL carrega, API pontua e alerta, e a decisão fica registrada na trilha de auditoria."""
    from fastapi.testclient import TestClient

    from api.database import get_db
    from api.main import app
    from ml.predictor import RiskPredictor

    db_path, conn = ambiente_e2e

    # 1. O ETL deixou a base íntegra e rastreável
    total_etl = conn.execute("SELECT COUNT(*) FROM telemetria WHERE fonte = 'dataset_simulado'").fetchone()[0]
    rastreaveis = conn.execute(
        "SELECT COUNT(*) FROM telemetria WHERE fonte = 'dataset_simulado' AND id_coleta IS NOT NULL"
    ).fetchone()[0]
    assert total_etl == rastreaveis > 0
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    equipamento = conn.execute(
        "SELECT id_equipamento FROM equipamentos ORDER BY id_equipamento LIMIT 1"
    ).fetchone()[0]

    # 2. API rodando contra o banco do ETL
    app.dependency_overrides[get_db] = lambda: conn
    app.state.predictor = RiskPredictor()
    client = TestClient(app)
    try:
        token = client.post(
            "/api/v1/login", json={"email": "fernanda@agrorisk.local", "senha": "gestor123"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "id_equipamento": equipamento,
            "id_coleta": 500001,
            "tipo_operacao": "Campo",
            "latitude": -13.4,
            "longitude": -56.0,
            "proximidade_agua_m": 40,
            "precipitacao_mm": 60.0,
            "umidade_solo_pct": 92.0,
            "tipo_solo": "Argiloso",
            "declividade_graus": 12.0,
            "temperatura_c": 29.0,
            "velocidade_vento_kmh": 20.0,
            "visibilidade_m": 800,
            "horas_uso_equipamento": 6000,
            "dias_ultima_manutencao": 90,
            "velocidade_operacao_kmh": 11.0,
            "carga_pct": 96.0,
            "nivel_combustivel_pct": 55.0,
            "historico_incidentes": 3,
        }

        # 3. Coleta entra, é pontuada (regra e modelo) e gera alerta
        resposta = client.post("/api/v1/telemetria", json=payload, headers=headers)
        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert 0 <= corpo["score_risco"] <= 100
        assert 0 <= corpo["score_risco_predito"] <= 100
        assert corpo["nivel_risco_predito"] in ("Baixo", "Médio", "Alto", "Crítico")
        assert isinstance(corpo["fatores_principais"], list)

        id_registro = corpo["id_registro"]
        persistido = conn.execute(
            "SELECT fonte, id_coleta, score_risco FROM telemetria WHERE id_registro = ?",
            (id_registro,),
        ).fetchone()
        assert (persistido["fonte"], persistido["id_coleta"]) == ("api", 500001)
        assert conn.execute(
            "SELECT COUNT(*) FROM scores_modelo WHERE id_registro = ?", (id_registro,)
        ).fetchone()[0] == 1

        # A regra decide o alerta (fonte única): o payload é Crítico pela regra, então o
        # registro TEM que estar no histórico auditável — mesmo que o modelo discorde.
        assert corpo["nivel_risco"] in ("Alto", "Crítico")
        assert corpo["alerta_gerado"] is True
        alerta = conn.execute(
            "SELECT nivel_risco, score_risco, mensagem FROM alertas WHERE id_registro = ?",
            (id_registro,),
        ).fetchone()
        assert alerta is not None
        assert alerta["nivel_risco"] == corpo["nivel_risco"]
        assert alerta["score_risco"] == corpo["score_risco"]
        assert "Fatores principais" in alerta["mensagem"]

        # 4. Reenvio da mesma coleta não duplica
        repetido = client.post("/api/v1/telemetria", json=payload, headers=headers)
        assert repetido.status_code == 409
        assert conn.execute(
            "SELECT COUNT(*) FROM telemetria WHERE id_coleta = 500001"
        ).fetchone()[0] == 1

        # 5. Leitura de volta: histórico, alertas e auditoria
        historico = client.get(f"/api/v1/telemetria?limit=5", headers=headers).json()
        assert any(linha["id_registro"] == id_registro for linha in historico)
        assert client.get("/api/v1/alertas", headers=headers).status_code == 200

        trilha = client.get("/api/v1/auditoria?acao=decisao_risco", headers=headers).json()
        assert trilha and all(evento["acao"] == "decisao_risco" for evento in trilha)
        assert f"score_modelo={corpo['score_risco_predito']}" in trilha[0]["detalhes"]
    finally:
        app.dependency_overrides.clear()


def test_etl_repetido_nao_duplica_nem_perde_registro(ambiente_e2e):
    """Reexecutar o pipeline sobre a base carregada mantém os totais e não cria duplicata natural."""
    from data import load_to_sql, pipeline

    db_path, conn = ambiente_e2e
    antes = conn.execute("SELECT COUNT(*) FROM telemetria").fetchone()[0]

    pipeline.processar_features()
    resultado = load_to_sql.carregar_dados()

    depois = conn.execute("SELECT COUNT(*) FROM telemetria").fetchone()[0]
    assert (resultado.inseridos, depois) == (0, antes)
    assert resultado.coletas_ja_presentes > 0
    assert conn.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM telemetria GROUP BY id_equipamento, data_hora HAVING COUNT(*) > 1)"
    ).fetchone()[0] == 0


def test_features_geradas_alimentam_o_modelo(ambiente_e2e):
    """O CSV tratado pelo ETL é aceito pelo modelo treinado — contrato entre #3 e #4."""
    from ml.predictor import RiskPredictor

    db_path, _conn = ambiente_e2e
    features = pd.read_csv(db_path.parent / "data" / "processed" / "features.csv").head(5)

    predicoes = RiskPredictor().predict(features)

    assert len(predicoes) == 5
    assert predicoes["score_risco_predito"].between(0, 100).all()
    assert len(set(predicoes["score_risco_predito"])) > 1
