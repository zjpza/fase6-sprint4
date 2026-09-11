from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from security.auth import get_current_user

UserDep = Annotated[dict, Depends(get_current_user)]


def require_role(role: str):
    def checker(user: UserDep) -> dict:
        if user["role"] != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso restrito ao papel: {role}",
            )
        return user
    return checker


def require_operador_or_gestor(user: UserDep) -> dict:
    if user["role"] not in ("Operador", "GestorFrota"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a Operador ou Gestor de Frota",
        )
    return user


def require_gestor_or_analista(user: UserDep) -> dict:
    if user["role"] not in ("GestorFrota", "AnalistaSeguradora"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a Gestor de Frota ou Analista",
        )
    return user