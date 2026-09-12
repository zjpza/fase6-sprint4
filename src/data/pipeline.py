"""Pipeline de ETL: schema → dataset simulado → features → carga no banco.

Executável de duas formas, a partir da raiz do projeto:
- ``python src/data/pipeline.py``
- ``python -m src.data.pipeline``
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

# Bootstrap para que `data.*` e `ml.*` resolvam nos dois modos de execução,
# sem depender de cwd=src/data (achado B4 da auditoria).
SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.conexao import conectar  # noqa: E402
from data.feature_engineering import OUTPUT_PATH, RAW_PATH, criar_features, salvar_scaler, validar_features  # noqa: E402
from data.generate_dataset import OUTPUT_PATH as RAW_OUTPUT, gerar_dataset  # noqa: E402
from data.load_to_sql import TABLE_NAME, ResultadoCarga, carregar_dados, contar_registros  # noqa: E402

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
    with conectar(DB_PATH) as conn:
        # Antes dos arquivos SQL: as bases antigas precisam das colunas de
        # rastreabilidade para os índices do schema novo aplicarem.
        atualizar_schema_legado(conn)
        for sql_file in SQL_FILES:
            if not sql_file.exists():
                raise FileNotFoundError(f"Arquivo SQL não encontrado: {sql_file}")
            conn.executescript(sql_file.read_text(encoding="utf-8"))
        conn.commit()
    print(f"[OK] Schema executado em {DB_PATH}")


def atualizar_schema_legado(conn: sqlite3.Connection) -> None:
    """Adiciona as colunas de rastreabilidade em bases criadas antes da Sprint 4.

    `CREATE TABLE IF NOT EXISTS` não altera tabela existente: sem esta migração,
    um `sompo.db` antigo ficaria sem `fonte`/`id_coleta` e a carga voltaria a
    perder a origem dos registros.
    """
    colunas = {coluna[1] for coluna in conn.execute(f"PRAGMA table_info({TABLE_NAME})")}
    if not colunas or "id_coleta" in colunas:
        return
    # As linhas que já existiam vêm de base anterior à rastreabilidade: rotulá-las
    # como 'api' (default do schema) inventaria procedência. Quem escreve agora
    # (API e ETL) informa a fonte explicitamente.
    conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN fonte TEXT NOT NULL DEFAULT 'legado'")
    conn.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN id_coleta INTEGER")
    conn.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_telemetria_rastreabilidade ON {TABLE_NAME}(fonte, id_coleta)"
    )
    print(f"[OK] Colunas de rastreabilidade adicionadas em {TABLE_NAME}")


def gerar_dados_brutos(n_registros: int = 1000) -> pd.DataFrame:
    """Gera dataset simulado e salva em data/raw/dataset_simulado.csv."""
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = gerar_dataset(n_registros)
    df.to_csv(RAW_OUTPUT, index=False)
    print(f"[OK] {len(df)} registros brutos salvos em {RAW_OUTPUT}")
    return df


def processar_features() -> pd.DataFrame:
    """Executa o feature engineering sobre o CSV bruto e salva os artefatos.

    Falha com mensagem clara se o CSV estiver ausente ou malformado —
    sem traceback cru no ponto de contato com o arquivo (spec #2).
    """
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not RAW_OUTPUT.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {RAW_OUTPUT}. Rode gerar_dados_brutos primeiro.")
    try:
        df_raw = pd.read_csv(RAW_OUTPUT, parse_dates=["data_hora"])
    except (ValueError, pd.errors.ParserError) as exc:
        raise ValueError(f"CSV bruto inválido ({RAW_OUTPUT}): {exc}") from exc
    df_features = criar_features(df_raw)
    validar_features(df_features)
    salvar_scaler(df_features)
    df_features.to_csv(OUTPUT_PATH, index=False)
    print(f"[OK] Features salvas em {OUTPUT_PATH}")
    return df_features


def carregar_banco() -> ResultadoCarga:
    """Carrega os dados processados no banco e devolve o resultado da carga."""
    resultado = carregar_dados()
    print(f"[OK] Carga: {resultado.resumo()}")
    return resultado


def run_pipeline(n_registros: int = 1000) -> None:
    """Executa o pipeline completo: schema → dados → features → banco."""
    executar_schema()
    gerar_dados_brutos(n_registros)
    processar_features()
    carregar_banco()
    print(f"[OK] Pipeline concluído com sucesso ({contar_registros()} registros em {TABLE_NAME}).")


if __name__ == "__main__":
    run_pipeline()
