"""Acesso ao banco SQLite (sompo.db) da API AgroRisk AI."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from data.conexao import conectar

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "sompo.db"


def get_connection() -> sqlite3.Connection:
    """Abre uma conexão com rows nomeadas, FKs habilitadas e espera por lock.

    Mesma política de conexão do ETL (`data.conexao`): sem o `busy_timeout`
    uma escrita concorrente (API + carga do ETL) falharia na hora.
    """
    return conectar(DB_PATH, check_same_thread=False)


def get_db() -> sqlite3.Connection:
    """Dependency do FastAPI: abre a conexão por request e garante o fechamento."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
