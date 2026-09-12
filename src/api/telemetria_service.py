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
    componentes_regra,
    faixa_proximidade,
    score_regra,
)
from ml.predictor import RiskPredictor
from ml.recomendacao import mensagem_alerta

# Identifica no banco que o registro veio da coleta ao vivo (não da carga do ETL).
FONTE_API = "api"


class ColetaDuplicada(Exception):
    """A mesma coleta (fonte + id_coleta) já está no banco — evita registro duplicado."""

    def __init__(self, id_registro: int) -> None:
        super().__init__(f"coleta já registrada em id_registro={id_registro}")
        self.id_registro = id_registro


def _buscar_coleta(conn: sqlite3.Connection, id_coleta: int | None) -> int | None:
    """Id do registro já gravado para esta coleta da API, se existir."""
    if id_coleta is None:
        return None
    linha = conn.execute(
        "SELECT id_registro FROM telemetria WHERE fonte = ? AND id_coleta = ?",
        (FONTE_API, id_coleta),
    ).fetchone()
    return int(linha[0]) if linha is not None else None


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
    # Procedência explícita: a coleta ao vivo identifica a fonte e, quando o cliente
    # informa o id da coleta, guarda esse id (id_coleta nulo = coleta sem id de origem).
    colunas.extend(["fonte", "id_coleta"])
    valores.extend([FONTE_API, dados.get("id_coleta")])
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


def _inserir_alerta(
    conn: sqlite3.Connection,
    id_registro: int,
    id_equipamento: str,
    nivel: str,
    score: int,
    mensagem: str,
) -> None:
    """Grava o alerta de risco Alto/Crítico da REGRA (fonte única de decisão)."""
    if nivel not in ("Alto", "Crítico"):
        return
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
    """Fluxo completo: insere telemetria, calcula score, prediz e registra alerta.

    Coleta já registrada (mesma `fonte` + `id_coleta`) não entra de novo: levanta
    ``ColetaDuplicada`` para a rota responder 409 com o registro existente.
    """
    row = calcular_features(dados)
    row["data_hora"] = datetime.now().isoformat()
    row["score_risco"] = score_regra(row)
    row["nivel_risco"] = classificar_risco(row["score_risco"])
    row["alerta_gerado"] = int(row["nivel_risco"] in ("Alto", "Crítico"))
    row["score_risco_calculado"] = row["score_risco"]
    row["diff_score"] = 0

    if row.get("id_coleta") is not None:
        existente = _buscar_coleta(conn, row["id_coleta"])
        if existente is not None:
            raise ColetaDuplicada(existente)

    try:
        id_registro = _inserir_telemetria(conn, row)
    except sqlite3.IntegrityError as exc:
        # Corrida entre dois envios da mesma coleta: o índice único (fonte, id_coleta) barra.
        existente = _buscar_coleta(conn, row.get("id_coleta"))
        if existente is not None:
            raise ColetaDuplicada(existente) from exc
        raise
    row["id_registro"] = id_registro

    df = pd.DataFrame([row])
    pred_df = predictor.predict(df)
    pred = pred_df.iloc[0].to_dict()
    pred["id_registro"] = id_registro
    pred["id_equipamento"] = row["id_equipamento"]

    _inserir_score_modelo(conn, pred)
    componentes = componentes_regra(row)
    msg = mensagem_alerta(
        row["nivel_risco"],
        componentes,
        {
            "nivel_risco_predito": pred["nivel_risco_predito"],
            "score_risco_predito": pred["score_risco_predito"],
        },
    )
    _inserir_alerta(
        conn,
        id_registro,
        row["id_equipamento"],
        row["nivel_risco"],
        row["score_risco"],
        msg,
    )
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
        "divergente": bool(row["nivel_risco"] != pred["nivel_risco_predito"]),
        "recomendacao": msg,
        "fatores_principais": fatores,
        "data_hora": row["data_hora"],
    }
