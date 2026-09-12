"""Conexão SQLite compartilhada pelo ETL: foreign keys ligadas e espera por lock.

Ponto único de configuração de conexão do lado de dados — evita repetir
`PRAGMA foreign_keys`/`busy_timeout` em cada script (issue #3).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

#: Tempo máximo que o SQLite espera por um lock antes de devolver "database is locked".
TIMEOUT_SEGUNDOS = 5.0


def conectar(db_path: Path | str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Abre a conexão com rows nomeadas, FKs e espera configurável por lock.

    O ``timeout`` do sqlite3 e o ``busy_timeout`` do próprio motor são o
    retry nativo para escritas concorrentes: em vez de falhar na hora,
    a conexão aguarda até o timeout antes de levantar ``OperationalError``.
    """
    conn = sqlite3.connect(db_path, timeout=TIMEOUT_SEGUNDOS, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {int(TIMEOUT_SEGUNDOS * 1000)}")
    return conn
