from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pandas as pd

from feature_engineering import OUTPUT_PATH, RAW_PATH, criar_features, salvar_scaler, validar_features
from generate_dataset import OUTPUT_PATH as RAW_OUTPUT, gerar_dataset

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "sompo.db"
SQL_FILES = [
    ROOT / "src" / "sql" / "01_schema.sql",
    ROOT / "src" / "sql" / "02_seed_data.sql",
    ROOT / "src" / "sql" / "03_views.sql",
    ROOT / "src" / "sql" / "04_queries_analiticas.sql",
    ROOT / "src" / "sql" / "05_audit_schema.sql",
]


def executar_schema() -> None:
    """Cria/atualiza o banco de dados executando os arquivos SQL na ordem."""
    conn = sqlite3.connect(DB_PATH)
    for sql_file in SQL_FILES:
        if not sql_file.exists():
            raise FileNotFoundError(f"Arquivo SQL não encontrado: {sql_file}")
        with sql_file.open("r", encoding="utf-8") as file:
            conn.executescript(file.read())
    conn.commit()
    conn.close()
    print(f"[OK] Schema executado em {DB_PATH}")


def gerar_dados_brutos(n_registros: int = 1000) -> pd.DataFrame:
    """Gera dataset simulado e salva em data/raw/dataset_simulado.csv."""
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = gerar_dataset(n_registros)
    df.to_csv(RAW_OUTPUT, index=False)
    print(f"[OK] {len(df)} registros brutos salvos em {RAW_OUTPUT}")
    return df


def processar_features() -> pd.DataFrame:
    """Executa o feature engineering e salva artefatos."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_raw = pd.read_csv(RAW_OUTPUT, parse_dates=["data_hora"])
    df_features = criar_features(df_raw)
    validar_features(df_features)
    salvar_scaler(df_features)
    df_features.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Features salvas em {OUTPUT_PATH}")
    return df_features


def carregar_banco() -> int:
    """Carrega os dados processados no banco via script existente."""
    load_script = Path(__file__).resolve().parent / "load_to_sql.py"
    result = subprocess.run(
        [sys.executable, str(load_script)],
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("Falha ao carregar dados no banco")
    return 0


def run_pipeline(n_registros: int = 1000) -> None:
    """Executa o pipeline completo: schema → dados → features → banco."""
    executar_schema()
    gerar_dados_brutos(n_registros)
    processar_features()
    carregar_banco()
    print("[OK] Pipeline concluído com sucesso.")


if __name__ == "__main__":
    run_pipeline()
