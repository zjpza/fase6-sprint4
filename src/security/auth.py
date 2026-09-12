from __future__ import annotations
import os
import secrets
import sqlite3
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext

from api.database import get_db

ROOT = Path(__file__).resolve().parents[2]

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def _carregar_env() -> None:
    """Carrega `.env` da raiz do projeto, se o python-dotenv estiver instalado."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env", override=False)


def _resolver_secret() -> str:
    """Segredo de assinatura do JWT: variável de ambiente → `.env` → segredo efêmero.

    Não existe segredo embutido no código: sem `JWT_SECRET_KEY` a API gera um
    segredo aleatório por processo (tokens deixam de valer entre reinícios) e
    avisa no log — o contrário do default fixo que era versionado (achado B10).
    """
    _carregar_env()
    secret = os.getenv("JWT_SECRET_KEY")
    if secret:
        if len(secret) < 32:
            warnings.warn(
                "JWT_SECRET_KEY com menos de 32 bytes — use um segredo mais longo em produção.",
                RuntimeWarning,
                stacklevel=1,
            )
        return secret

    efemero = secrets.token_urlsafe(32)
    warnings.warn(
        "JWT_SECRET_KEY não definida — usando segredo aleatório só deste processo. "
        "Defina JWT_SECRET_KEY no .env (veja .env.example) para manter os tokens válidos "
        "entre reinícios da API.",
        RuntimeWarning,
        stacklevel=1,
    )
    return efemero


SECRET_KEY = _resolver_secret()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

bearer_scheme = HTTPBearer(auto_error=False)


def authenticate(conn: sqlite3.Connection, email: str, senha: str) -> dict | None:
    row = conn.execute(
        "SELECT id_usuario, nome, email, role, id_equipamento_acesso, senha_hash "
        "FROM usuarios WHERE email = ? AND ativo = 1",
        (email,),
    ).fetchone()
    if row is None:
        return None
    if not pwd_context.verify(senha, row["senha_hash"]):
        return None
    return {
        "id_usuario": row["id_usuario"],
        "nome": row["nome"],
        "email": row["email"],
        "role": row["role"],
        "id_equipamento_acesso": row["id_equipamento_acesso"],
    }


def get_user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    row = conn.execute(
        "SELECT id_usuario, nome, email, role, id_equipamento_acesso "
        "FROM usuarios WHERE email = ?",
        (email,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def create_access_token(user: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user["email"],
        "id_usuario": user["id_usuario"],
        "role": user["role"],
        "id_equipamento_acesso": user.get("id_equipamento_acesso"),
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        user = get_user_by_email(conn, email)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")