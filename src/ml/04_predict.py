"""Predição em lote sobre a telemetria do banco — demonstração sem passar pela API.

Usa o mesmo `RiskPredictor` da API: score contínuo (média das faixas ponderada pelas
probabilidades) e fatores por contribuição saem de uma implementação só, sem lógica
de score duplicada neste script.

Executar a partir da raiz do projeto:

``python src/ml/04_predict.py``
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.conexao import conectar  # noqa: E402
from ml.predictor import RiskPredictor  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "sompo.db"


def main() -> None:
    with conectar(DB_PATH) as conn:
        df = pd.read_sql("SELECT * FROM telemetria", conn)
        if df.empty:
            raise SystemExit("Telemetria vazia — rode o ETL (python src/data/pipeline.py) antes.")

        predictor = RiskPredictor()
        predicoes = predictor.predict(df)
        agora = datetime.now().isoformat()

        registros = [
            (
                int(linha["id_registro"]),
                str(linha["id_equipamento"]),
                agora,
                int(linha["score_risco_predito"]),
                str(linha["nivel_risco_predito"]),
                int(linha["alerta_predito"]),
                str(linha["modelo_utilizado"]),
                str(linha["probabilidades"]),
                str(linha["fatores_principais"]),
            )
            for _, linha in predicoes.iterrows()
        ]

        # Reexecutar reescreve as predições dos mesmos registros, sem acumular duplicatas.
        ids = [registro[0] for registro in registros]
        conn.executemany("DELETE FROM scores_modelo WHERE id_registro = ?", [(i,) for i in ids])
        conn.executemany(
            """
            INSERT INTO scores_modelo
                (id_registro, id_equipamento, data_hora_predicao, score_risco_predito,
                 nivel_risco_predito, alerta_predito, modelo_utilizado, probabilidades, fatores_principais)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros,
        )
        conn.commit()

    print(f"[OK] {len(registros)} predições gravadas em scores_modelo ({predictor.model_name})")
    print(predicoes["nivel_risco_predito"].value_counts().to_string())


if __name__ == "__main__":
    main()
