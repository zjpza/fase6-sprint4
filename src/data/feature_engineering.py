from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from generate_dataset import calcular_score

# Bootstrap para importar ml.features quando executado via `python src/data/...`.
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ml.features import (  # noqa: E402
    FAIXA_ENCODER,
    OPERACAO_ENCODER,
    SOLO_ENCODER,
    faixa_proximidade,
)


ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = ROOT / "data" / "raw" / "dataset_simulado.csv"
OUTPUT_PATH = ROOT / "data" / "processed" / "features.csv"
SCALER_PATH = Path(__file__).resolve().parent / "scaler.pkl"
ENCODERS_PATH = Path(__file__).resolve().parent / "label_encoders.pkl"

def criar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["tipo_solo_encoded"] = df["tipo_solo"].map(SOLO_ENCODER).astype(int)
    df["tipo_operacao_encoded"] = df["tipo_operacao"].map(OPERACAO_ENCODER).astype(int)
    df["faixa_proximidade_agua"] = df["proximidade_agua_m"].apply(faixa_proximidade)
    df["faixa_proximidade_encoded"] = df["faixa_proximidade_agua"].map(FAIXA_ENCODER).astype(int)
    df["indice_desgaste"] = df["horas_uso_equipamento"] / df["dias_ultima_manutencao"].clip(lower=1)
    df["risco_solo"] = (
        (df["umidade_solo_pct"] * df["tipo_solo_encoded"]) / df["declividade_graus"].replace(0, 0.1)
    ).replace([np.inf, -np.inf], 0)
    df["risco_atolamento"] = (
        df["faixa_proximidade_encoded"] * 25
        + df["umidade_solo_pct"] * 0.35
        + df["precipitacao_mm"] * 0.25
        + df["tipo_solo_encoded"] * 8
    )
    df["risco_operacional"] = (
        df["velocidade_operacao_kmh"] * np.where(df["tipo_operacao"] == "Campo", 3, 0.6)
        + df["carga_pct"] * 0.3
        + df["declividade_graus"] * 2
        + np.maximum(0, 1000 - df["visibilidade_m"]) * 0.02
    )
    df["risco_manutencao"] = (
        df["horas_uso_equipamento"] / 120
        + df["dias_ultima_manutencao"] * 0.35
        + df["historico_incidentes"] * 9
    )
    df["score_risco_calculado"] = df.apply(lambda row: calcular_score(row.to_dict()), axis=1).astype(int)
    df["diff_score"] = (df["score_risco_calculado"] - df["score_risco"]).abs()
    return df


def salvar_scaler(df: pd.DataFrame) -> None:
    colunas_para_escalar = [
        "proximidade_agua_m",
        "precipitacao_mm",
        "umidade_solo_pct",
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
        "indice_desgaste",
        "risco_solo",
        "risco_atolamento",
        "risco_operacional",
        "risco_manutencao",
    ]
    scaler = MinMaxScaler()
    scaler.fit(df[colunas_para_escalar])
    with SCALER_PATH.open("wb") as file:
        pickle.dump({"scaler": scaler, "columns": colunas_para_escalar}, file)
    with ENCODERS_PATH.open("wb") as file:
        pickle.dump(
            {
                "tipo_solo": SOLO_ENCODER,
                "tipo_operacao": OPERACAO_ENCODER,
                "faixa_proximidade_agua": FAIXA_ENCODER,
            },
            file,
        )


def validar_features(df: pd.DataFrame) -> None:
    assert not df.isna().any().any()
    assert df["score_risco"].between(0, 100).all()
    assert df["diff_score"].max() <= 6
    assert not ((df["alerta_gerado"]) & (df["nivel_risco"] == "Baixo")).any()


def main() -> None:
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {RAW_PATH}. Rode generate_dataset.py primeiro.")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(RAW_PATH)
    features = criar_features(df)
    validar_features(features)
    salvar_scaler(features)
    features.to_csv(OUTPUT_PATH, index=False)
    print(f"Features salvas em {OUTPUT_PATH} com {len(features)} registros")


if __name__ == "__main__":
    main()
