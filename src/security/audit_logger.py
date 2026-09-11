from __future__ import annotations

import sqlite3
from datetime import datetime


def log(
    conn: sqlite3.Connection,
    *,
    id_usuario: int | None = None,
    acao: str,
    recurso: str | None = None,
    id_equipamento: str | None = None,
    id_registro: int | None = None,
    detalhes: str | None = None,
    ip_origem: str | None = None,
) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO auditoria
            (id_usuario, acao, recurso, id_equipamento, id_registro, detalhes, ip_origem, data_hora)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id_usuario,
            acao,
            recurso,
            id_equipamento,
            id_registro,
            detalhes,
            ip_origem,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
