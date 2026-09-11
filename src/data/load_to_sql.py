from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = ROOT / "data" / "processed" / "features.csv"
DB_PATH = ROOT / "sompo.db"
TABLE_NAME = "telemetria"
EQUIPAMENTOS_SEED = [
    ("EQ-MT-0023", "Colheitadeira", "MT", -13.4295, -56.7891, 2019, 15000),
    ("EQ-MT-0031", "Trator", "MT", -13.4310, -56.7910, 2021, 8000),
    ("EQ-GO-0012", "Pulverizador", "GO", -17.8821, -51.0932, 2020, 5000),
    ("EQ-SP-0008", "Trator", "SP", -22.9105, -47.0626, 2022, 9000),
    ("EQ-RS-0019", "Trator", "RS", -30.0346, -51.2177, 2018, 7500),
]


def carregar_equipamentos(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    colunas = conn.execute("PRAGMA table_info(equipamentos)").fetchall()
    if not colunas:
        return

    # Usa os equipamentos seed como base, complementando com os do dataset.
    seed_df = pd.DataFrame(
        EQUIPAMENTOS_SEED,
        columns=[
            "id_equipamento",
            "tipo_equipamento",
            "estado_uf",
            "latitude_base",
            "longitude_base",
            "ano_fabricacao",
            "capacidade_carga_kg",
        ],
    )
    dataset_equipamentos = (
        df.groupby("id_equipamento")
        .agg(
            tipo_equipamento=("tipo_equipamento", "first"),
            latitude_base=("latitude", "mean"),
            longitude_base=("longitude", "mean"),
        )
        .reset_index()
    )
    dataset_equipamentos["estado_uf"] = dataset_equipamentos["id_equipamento"].str.split("-").str[1]
    dataset_equipamentos["ano_fabricacao"] = 2020
    dataset_equipamentos["capacidade_carga_kg"] = dataset_equipamentos["tipo_equipamento"].map(
        {"Colheitadeira": 15000, "Trator": 8000, "Pulverizador": 5000}
    )

    # Prioriza os dados seed, adiciona novos equipamentos do dataset.
    merged = pd.concat(
        [seed_df, dataset_equipamentos[["id_equipamento", "tipo_equipamento", "estado_uf", "latitude_base", "longitude_base", "ano_fabricacao", "capacidade_carga_kg"]]],
        ignore_index=True,
    ).drop_duplicates(subset=["id_equipamento"], keep="first")

    conn.executemany(
        """
        INSERT OR IGNORE INTO equipamentos
            (id_equipamento, tipo_equipamento, estado_uf, latitude_base, longitude_base, ano_fabricacao, capacidade_carga_kg)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        merged.itertuples(index=False, name=None),
    )


def obter_colunas_tabela(conn: sqlite3.Connection) -> list[str]:
    colunas = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    if not colunas:
        raise RuntimeError(f"Tabela '{TABLE_NAME}' não existe em {DB_PATH}. Crie o schema SQL antes da carga.")
    return [coluna[1] for coluna in colunas]


def preparar_dataframe(df: pd.DataFrame, colunas_tabela: list[str]) -> pd.DataFrame:
    df = df.copy()
    if "alerta_gerado" in df.columns:
        df["alerta_gerado"] = df["alerta_gerado"].astype(bool).astype(int)

    colunas_geradas_banco = {"data_ingestao"}
    if "id_registro" not in colunas_tabela:
        colunas_geradas_banco.add("id_registro")

    colunas_insert = [col for col in colunas_tabela if col in df.columns and col not in colunas_geradas_banco]
    return df[colunas_insert]


def carregar_dados() -> int:
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {FEATURES_PATH}. Rode feature_engineering.py primeiro.")

    df = pd.read_csv(FEATURES_PATH)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        carregar_equipamentos(conn, df)
        colunas_tabela = obter_colunas_tabela(conn)
        dados = preparar_dataframe(df, colunas_tabela)
        placeholders = ", ".join(["?"] * len(dados.columns))
        colunas_sql = ", ".join(dados.columns)
        sql = f"INSERT OR IGNORE INTO {TABLE_NAME} ({colunas_sql}) VALUES ({placeholders})"
        antes = conn.total_changes
        conn.executemany(sql, dados.itertuples(index=False, name=None))
        conn.commit()
        return conn.total_changes - antes


def main() -> None:
    inseridos = carregar_dados()
    print(f"{inseridos} registros inseridos em {DB_PATH}:{TABLE_NAME}")


if __name__ == "__main__":
    main()
