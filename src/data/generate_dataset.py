from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


SEED = 42
ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = ROOT / "data" / "raw" / "dataset_simulado.csv"

UF_COORDS = {
    "MT": (-13.4, -56.0),
    "GO": (-16.0, -49.8),
    "BA": (-12.5, -45.0),
    "RS": (-29.5, -53.5),
    "PR": (-24.7, -51.5),
    "SP": (-22.5, -48.5),
}
TIPOS_EQUIPAMENTO = ["Colheitadeira", "Trator", "Pulverizador"]
TIPOS_SOLO = ["Argiloso", "Arenoso", "Misto"]


def gerar_ruido_score(row: dict) -> int:
    id_registro = row.get("id_registro")
    if id_registro is None:
        return random.randint(-3, 3)
    return random.Random(SEED + int(id_registro)).randint(-3, 3)


def gerar_precipitacao() -> float:
    faixa = np.random.choice(["seco", "moderado", "forte", "temporal"], p=[0.60, 0.25, 0.10, 0.05])
    limites = {
        "seco": (0, 5),
        "moderado": (5, 30),
        "forte": (30, 60),
        "temporal": (60, 100),
    }[faixa]
    return round(float(np.random.uniform(*limites)), 1)


def gerar_declividade() -> float:
    faixa = np.random.choice(["plano", "moderado", "ingreme"], p=[0.60, 0.30, 0.10])
    limites = {"plano": (0, 5), "moderado": (5, 12), "ingreme": (12, 22)}[faixa]
    return round(float(np.random.uniform(*limites)), 1)


def calcular_umidade_solo(tipo_solo: str, precipitacao_mm: float) -> float:
    noise = np.random.normal(0, 4)
    if tipo_solo == "Argiloso":
        umidade = 45 + (precipitacao_mm * 0.8) + noise
    elif tipo_solo == "Arenoso":
        umidade = 20 + (precipitacao_mm * 0.3) + noise
    else:
        umidade = 30 + (precipitacao_mm * 0.5) + noise

    if tipo_solo == "Argiloso" and precipitacao_mm > 50:
        umidade = max(umidade, 76)
    return round(float(np.clip(umidade, 5, 100)), 1)


def gerar_visibilidade(precipitacao_mm: float) -> int:
    base = 5000 - (precipitacao_mm * 55) + np.random.normal(0, 250)
    return int(np.clip(base, 150, 5000))


def gerar_proximidade_agua(tipo_operacao: str) -> int:
    if tipo_operacao == "Transporte":
        return int(np.random.uniform(5000, 10000))

    faixa = np.random.choice(["baixo", "medio", "alto", "critico"], p=[0.40, 0.25, 0.20, 0.15])
    limites = {
        "baixo": (500, 2500),
        "medio": (200, 500),
        "alto": (50, 200),
        "critico": (5, 50),
    }[faixa]
    return int(np.random.uniform(*limites))


def calcular_score(row: dict) -> int:
    score = 0
    if row["proximidade_agua_m"] < 50:
        score += 30
    elif row["proximidade_agua_m"] < 200:
        score += 20
    elif row["proximidade_agua_m"] < 500:
        score += 10

    if row["tipo_solo"] == "Argiloso" and row["umidade_solo_pct"] > 70:
        score += 25
    elif row["tipo_solo"] == "Argiloso" and row["umidade_solo_pct"] > 50:
        score += 15
    elif row["tipo_solo"] == "Misto" and row["umidade_solo_pct"] > 70:
        score += 15
    elif row["tipo_solo"] == "Arenoso" and row["umidade_solo_pct"] > 60:
        score += 5

    if row["declividade_graus"] > 15:
        score += 10
    elif row["declividade_graus"] > 10:
        score += 7
    elif row["declividade_graus"] > 5:
        score += 3

    if row["precipitacao_mm"] > 60:
        score += 10
    elif row["precipitacao_mm"] > 30:
        score += 7
    elif row["precipitacao_mm"] > 10:
        score += 3

    if row["velocidade_operacao_kmh"] > 10 and row["tipo_operacao"] == "Campo":
        score += 10
    elif row["velocidade_operacao_kmh"] > 8 and row["tipo_operacao"] == "Campo":
        score += 5
    if row["carga_pct"] > 95:
        score += 5

    if row["dias_ultima_manutencao"] > 60:
        score += 7
    if row["horas_uso_equipamento"] > 5000 and row["dias_ultima_manutencao"] > 45:
        score += 5
    if row["historico_incidentes"] >= 3:
        score += 8
    elif row["historico_incidentes"] >= 1:
        score += 3

    if row["nivel_combustivel_pct"] < 15:
        score += 3
    if row["visibilidade_m"] < 500 and row["tipo_operacao"] == "Transporte":
        score += 5

    if row["tipo_operacao"] == "Campo":
        score += 10
        if row["proximidade_agua_m"] < 50 and row["umidade_solo_pct"] > 60:
            score += 22
        elif row["proximidade_agua_m"] < 200 and row["umidade_solo_pct"] > 55:
            score += 14
        elif row["proximidade_agua_m"] < 500 and row["umidade_solo_pct"] > 65:
            score += 8
    if row["tipo_solo"] == "Argiloso" and row["precipitacao_mm"] > 60:
        score += 12
    if row["dias_ultima_manutencao"] > 90 and row["historico_incidentes"] >= 2:
        score += 8

    if (
        row["carga_pct"] > 95
        and row["declividade_graus"] > 10
        and row["tipo_solo"] == "Argiloso"
        and row["umidade_solo_pct"] > 70
    ):
        score = max(score, 56)

    if row["tipo_operacao"] == "Campo":
        score = round(score * 1.45)

    return int(np.clip(score + gerar_ruido_score(row), 0, 100))


def classificar_risco(score: int) -> str:
    if score <= 25:
        return "Baixo"
    if score <= 50:
        return "Médio"
    if score <= 75:
        return "Alto"
    return "Crítico"


def criar_equipamentos(total: int = 45) -> list[dict]:
    equipamentos = []
    for i in range(1, total + 1):
        uf = random.choice(list(UF_COORDS))
        lat, lon = UF_COORDS[uf]
        equipamentos.append(
            {
                "id_equipamento": f"EQ-{uf}-{i:04d}",
                "uf": uf,
                "tipo_equipamento": np.random.choice(TIPOS_EQUIPAMENTO, p=[0.40, 0.35, 0.25]),
                "base_latitude": lat + np.random.uniform(-0.8, 0.8),
                "base_longitude": lon + np.random.uniform(-0.8, 0.8),
            }
        )
    return equipamentos


def gerar_dataset(n_registros: int) -> pd.DataFrame:
    random.seed(SEED)
    np.random.seed(SEED)
    equipamentos = criar_equipamentos()
    inicio = datetime(2024, 1, 1, 6, 0, 0)
    registros = []

    for id_registro in range(1, n_registros + 1):
        equipamento = random.choice(equipamentos)
        tipo_operacao = np.random.choice(["Campo", "Transporte"], p=[0.70, 0.30])
        tipo_solo = np.random.choice(TIPOS_SOLO, p=[0.40, 0.35, 0.25])
        precipitacao = gerar_precipitacao()
        umidade = calcular_umidade_solo(tipo_solo, precipitacao)
        dias_ultima_manutencao = int(np.random.randint(1, 121))
        historico_base = np.random.poisson(max(0.2, dias_ultima_manutencao / 45))
        historico_incidentes = int(np.clip(historico_base, 0, 5))

        row = {
            "id_registro": id_registro,
            "id_equipamento": equipamento["id_equipamento"],
            "tipo_equipamento": equipamento["tipo_equipamento"],
            "data_hora": (inicio + timedelta(hours=int(np.random.randint(0, 24 * 180)))).strftime("%Y-%m-%d %H:%M:%S"),
            "latitude": round(float(equipamento["base_latitude"] + np.random.uniform(-0.005, 0.005)), 6),
            "longitude": round(float(equipamento["base_longitude"] + np.random.uniform(-0.005, 0.005)), 6),
            "tipo_operacao": tipo_operacao,
            "proximidade_agua_m": gerar_proximidade_agua(tipo_operacao),
            "precipitacao_mm": precipitacao,
            "umidade_solo_pct": umidade,
            "tipo_solo": tipo_solo,
            "declividade_graus": gerar_declividade(),
            "temperatura_c": round(float(np.random.uniform(18, 34) if equipamento["uf"] in ["RS", "PR", "SP"] else np.random.uniform(24, 40)), 1),
            "velocidade_vento_kmh": round(float(np.random.uniform(5, 55)), 1),
            "visibilidade_m": gerar_visibilidade(precipitacao),
            "horas_uso_equipamento": int(np.random.randint(500, 8001)),
            "dias_ultima_manutencao": dias_ultima_manutencao,
            "velocidade_operacao_kmh": round(float(np.random.uniform(3, 12) if tipo_operacao == "Campo" else np.random.uniform(40, 65)), 1),
            "carga_pct": round(float(np.random.uniform(30, 100)), 1),
            "nivel_combustivel_pct": round(float(np.random.uniform(10, 100)), 1),
            "historico_incidentes": historico_incidentes,
        }
        row["score_risco"] = calcular_score(row)
        row["nivel_risco"] = classificar_risco(row["score_risco"])
        row["alerta_gerado"] = row["nivel_risco"] in ["Alto", "Crítico"]
        registros.append(row)

    df = pd.DataFrame(registros)
    validar_dataset(df)
    return df


def validar_dataset(df: pd.DataFrame) -> None:
    assert len(df) >= 500
    assert df["score_risco"].between(0, 100).all()
    assert not ((df["alerta_gerado"]) & (df["nivel_risco"] == "Baixo")).any()
    assert (df.loc[df["tipo_operacao"] == "Transporte", "velocidade_operacao_kmh"] >= 40).all()
    assert (df.loc[df["tipo_operacao"] == "Campo", "velocidade_operacao_kmh"] <= 12).all()
    filtro = (df["tipo_solo"] == "Argiloso") & (df["precipitacao_mm"] > 50)
    assert (df.loc[filtro, "umidade_solo_pct"] > 75).all()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=1000)
    args = parser.parse_args()
    n_registros = max(args.n, 500)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = gerar_dataset(n_registros)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Dataset salvo em {OUTPUT_PATH} com {len(df)} registros")
    print(df["nivel_risco"].value_counts(normalize=True).mul(100).round(1).to_dict())


if __name__ == "__main__":
    main()
