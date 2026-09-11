import sys
from pathlib import Path

# Adiciona src ao PYTHONPATH para que os pacotes api, ml e security sejam encontrados.
SRC = Path(__file__).resolve().parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from api.main import app  # noqa: E402

__all__ = ["app"]
