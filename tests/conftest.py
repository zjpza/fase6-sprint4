"""Fixtures compartilhadas: banco SQLite temporário + TestClient com override de get_db."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# Reproduz o bootstrap de PYTHONPATH de start_api.py: adiciona src/ para que
# `from api...`, `from security...` e `from ml...` resolvam.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SQL_DIR = SRC / "sql"


@pytest.fixture
def db(tmp_path: Path) -> sqlite3.Connection:
    """Cria um banco SQLite em arquivo temporário com schema + seeds + auditoria."""
    conn = sqlite3.connect(tmp_path / "test.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    for script in ("01_schema.sql", "02_seed_data.sql", "03_views.sql", "05_audit_schema.sql"):
        conn.executescript((SQL_DIR / script).read_text(encoding="utf-8"))
    yield conn
    conn.close()


@pytest.fixture
def client(db: sqlite3.Connection):
    """TestClient da API com get_db sobrescrito para usar o banco temporário."""
    from api.database import get_db
    from api.main import app
    from ml.predictor import RiskPredictor
    from fastapi.testclient import TestClient

    def _override_get_db() -> sqlite3.Connection:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    app.state.predictor = RiskPredictor()
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()