from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
import sqlite3

from ml.features import (
    FAIXA_ENCODER,
    OPERACAO_ENCODER,
    SOLO_ENCODER,
    calcular_features,
    classificar_risco,
    faixa_proximidade,
    score_regra,
)
from ml.predictor import RiskPredictor
from ml.recomendacao import recomendar


def _inserir_telemetria(conn: sqlite3.Connection, dados: dict) -> int:
    colunas = [
        "id_equipamento",
        "data_hora",
        "latitude",
        "longitude",
        "tipo_operacao",
        "proximidade_agua_m",
        "precipitacao_mm",
        "umidade_solo_pct",
        "tipo_solo",
        "declividade_graus",
        "temperatura_c",
        "velocidade_vento_kmh",
        "visibilidade_m",
        "horas_uso_equipamento",
        "dias_ultima_manutencao",
        "velocidade_operacao_kmh",
        "carga_pct",
        "nivel_combustivel_pct",
        "historico_incidentes",
        "score_risco",
        "nivel_risco",
        "alerta_gerado",
        "tipo_solo_encoded",
        "tipo_operacao_encoded",
        "faixa_proximidade_agua",
        "faixa_proximidade_encoded",
        "indice_desgaste",
        "risco_solo",
        "risco_atolamento",
        "risco_operacional",
        "risco_manutencao",
        "score_risco_calculado",
        "diff_score",
    ]
    valores = [dados.get(col) for col in colunas]
    placeholders = ", ".join(["?"] * len(colunas))
    sql = f"INSERT INTO telemetria ({', '.join(colunas)}) VALUES ({placeholders})"
    cursor = conn.cursor()
    cursor.execute(sql, valores)
    return cursor.lastrowid


def _inserir_score_modelo(conn: sqlite3.Connection, pred: dict) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO scores_modelo
            (id_registro, id_equipamento, data_hora_predicao, score_risco_predito,
             nivel_risco_predito, alerta_predito, modelo_utilizado, probabilidades, fatores_principais)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pred["id_registro"],
            pred["id_equipamento"],
            datetime.now().isoformat(),
            pred["score_risco_predito"],
            pred["nivel_risco_predito"],
            pred["alerta_predito"],
            pred["modelo_utilizado"],
            pred["probabilidades"],
            pred["fatores_principais"],
        ),
    )


def _inserir_alerta(conn: sqlite3.Connection, id_registro: int, id_equipamento: str, nivel: str, score: int) -> None:
    if nivel not in ("Alto", "Crítico"):
        return
    mensagem = recomendar(nivel)
    tipo_alerta = "Crítico" if nivel == "Crítico" else "Preventivo"
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO alertas (id_registro, id_equipamento, nivel_risco, score_risco, mensagem, tipo_alerta)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (id_registro, id_equipamento, nivel, score, mensagem, tipo_alerta),
    )


def processar_telemetria(conn: sqlite3.Connection, dados: dict, predictor: RiskPredictor) -> dict:
    """Fluxo completo: insere telemetria, calcula score, prediz e registra alerta."""
    row = calcular_features(dados)
    row["data_hora"] = datetime.now().isoformat()
    row["score_risco"] = score_regra(row)
    row["nivel_risco"] = classificar_risco(row["score_risco"])
    row["alerta_gerado"] = int(row["nivel_risco"] in ("Alto", "Crítico"))
    row["score_risco_calculado"] = row["score_risco"]
    row["diff_score"] = 0

    id_registro = _inserir_telemetria(conn, row)
    row["id_registro"] = id_registro

    df = pd.DataFrame([row])
    pred_df = predictor.predict(df)
    pred = pred_df.iloc[0].to_dict()
    pred["id_registro"] = id_registro
    pred["id_equipamento"] = row["id_equipamento"]

    _inserir_score_modelo(conn, pred)
    _inserir_alerta(conn, id_registro, row["id_equipamento"], pred["nivel_risco_predito"], pred["score_risco_predito"])
    conn.commit()

    fatores = json.loads(pred["fatores_principais"])
    return {
        "id_registro": id_registro,
        "id_equipamento": row["id_equipamento"],
        "score_risco": row["score_risco"],
        "nivel_risco": row["nivel_risco"],
        "alerta_gerado": bool(row["alerta_gerado"]),
        "score_risco_predito": pred["score_risco_predito"],
        "nivel_risco_predito": pred["nivel_risco_predito"],
        "alerta_predito": bool(pred["alerta_predito"]),
        "recomendacao": recomendar(pred["nivel_risco_predito"], fatores),
        "fatores_principais": fatores,
        "data_hora": row["data_hora"],
    }
