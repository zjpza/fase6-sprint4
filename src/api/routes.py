from __future__ import annotations

from typing import Annotated

import sqlite3
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.database import get_db
from api.schemas import (
    AlertaResponse,
    EquipamentoResponse,
    LoginInput,
    TelemetriaHistoricoResponse,
    TelemetriaInput,
    TelemetriaResponse,
    TokenResponse,
    UserResponse,
)
from api.telemetria_service import processar_telemetria
from security.audit_logger import log
from security.auth import authenticate, create_access_token, get_current_user
from security.rbac import require_operador_or_gestor

router = APIRouter(prefix="/api/v1")


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginInput,
    request: Request,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
):
    user = authenticate(db, payload.email, payload.senha)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    log(
        db,
        id_usuario=user["id_usuario"],
        acao="login",
        recurso="/api/v1/login",
        detalhes=f"Login realizado por {user['nome']}",
        ip_origem=_get_client_ip(request),
    )
    return {"access_token": create_access_token(user), "token_type": "bearer"}

@router.get("/me", response_model=UserResponse)
def me(user: dict = Depends(get_current_user)):
    """Retorna o usuário autenticado a partir do token JWT (validado server-side)."""
    return user


@router.get("/equipamentos", response_model=list[EquipamentoResponse])
def listar_equipamentos(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    request: Request,
    user: dict = Depends(get_current_user),
):
    log(
        db,
        id_usuario=user["id_usuario"],
        acao="listar_equipamentos",
        recurso="/api/v1/equipamentos",
        ip_origem=_get_client_ip(request),
    )
    cursor = db.execute("SELECT * FROM equipamentos")
    return [dict(row) for row in cursor.fetchall()]

@router.get("/resumo-frota")
def resumo_frota(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Resumo de risco por equipamento (consome a view vw_resumo_risco_equipamento)."""
    cursor = db.execute("SELECT * FROM vw_resumo_risco_equipamento ORDER BY score_medio DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    log(
        db,
        id_usuario=user["id_usuario"],
        acao="resumo_frota",
        recurso="/api/v1/resumo-frota",
        ip_origem=_get_client_ip(request),
    )
    return rows


@router.get("/equipamentos/{id_equipamento}/risco")
def risco_equipamento(
    id_equipamento: str,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    request: Request,
    user: dict = Depends(get_current_user),
):
    if user["role"] == "Operador" and user.get("id_equipamento_acesso") != id_equipamento:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado a este equipamento")

    cursor = db.execute(
        """
        SELECT t.*, sm.nivel_risco_predito, sm.score_risco_predito
        FROM telemetria t
        LEFT JOIN scores_modelo sm ON t.id_registro = sm.id_registro
        WHERE t.id_equipamento = ?
        ORDER BY t.data_hora DESC
        LIMIT 1
        """,
        (id_equipamento,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Equipamento não encontrado ou sem telemetria")

    log(
        db,
        id_usuario=user["id_usuario"],
        acao="consultar_risco",
        recurso=f"/api/v1/equipamentos/{id_equipamento}/risco",
        id_equipamento=id_equipamento,
        ip_origem=_get_client_ip(request),
    )
    return dict(row)


@router.get("/alertas", response_model=list[AlertaResponse])
def listar_alertas(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    request: Request,
    user: dict = Depends(get_current_user),
):
    if user["role"] == "Operador":
        id_equipamento = user.get("id_equipamento_acesso")
        cursor = db.execute(
            "SELECT * FROM alertas WHERE id_equipamento = ? ORDER BY data_hora_alerta DESC",
            (id_equipamento,),
        )
    else:
        cursor = db.execute("SELECT * FROM alertas ORDER BY data_hora_alerta DESC LIMIT 100")

    log(
        db,
        id_usuario=user["id_usuario"],
        acao="listar_alertas",
        recurso="/api/v1/alertas",
        ip_origem=_get_client_ip(request),
    )
    return [dict(row) for row in cursor.fetchall()]
@router.get("/telemetria", response_model=list[TelemetriaHistoricoResponse])
def listar_telemetria(
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    request: Request,
    user: dict = Depends(get_current_user),
    id_equipamento: str | None = None,
    limit: int = 1000,
):
    """Retorna histórico de telemetria com dados de equipamento e predição do modelo.

    Operadores veem apenas os registros do seu equipamento; Gestores e Analistas
    veem toda a frota. Use ``id_equipamento`` para filtrar e ``limit`` para paginar.
    """
    if user["role"] == "Operador":
        id_equipamento = user.get("id_equipamento_acesso")

    query = """
        SELECT  t.id_registro, t.id_equipamento, t.data_hora, t.latitude, t.longitude,
                t.tipo_operacao, t.proximidade_agua_m, t.precipitacao_mm, t.umidade_solo_pct,
                t.tipo_solo, t.declividade_graus, t.temperatura_c, t.velocidade_vento_kmh,
                t.visibilidade_m, t.horas_uso_equipamento, t.dias_ultima_manutencao,
                t.velocidade_operacao_kmh, t.carga_pct, t.nivel_combustivel_pct,
                t.historico_incidentes, t.score_risco, t.nivel_risco, t.alerta_gerado,
                e.tipo_equipamento, e.estado_uf,
                sm.nivel_risco_predito, sm.score_risco_predito, sm.modelo_utilizado
        FROM telemetria t
        LEFT JOIN equipamentos e ON t.id_equipamento = e.id_equipamento
        LEFT JOIN scores_modelo sm ON t.id_registro = sm.id_registro
    """
    params: list = []
    if id_equipamento:
        query += " WHERE t.id_equipamento = ?"
        params.append(id_equipamento)
    query += " ORDER BY t.data_hora DESC LIMIT ?"
    params.append(limit)

    cursor = db.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]

    log(
        db,
        id_usuario=user["id_usuario"],
        acao="listar_telemetria",
        recurso="/api/v1/telemetria",
        id_equipamento=id_equipamento,
        detalhes=f"registros={len(rows)}; limit={limit}",
        ip_origem=_get_client_ip(request),
    )
    return rows


@router.post("/telemetria", response_model=TelemetriaResponse, status_code=status.HTTP_201_CREATED)
def receber_telemetria(
    payload: TelemetriaInput,
    db: Annotated[sqlite3.Connection, Depends(get_db)],
    request: Request,
    user: dict = Depends(require_operador_or_gestor),
):
    if user["role"] == "Operador" and user.get("id_equipamento_acesso") != payload.id_equipamento:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operador não autorizado para este equipamento")
    predictor = request.app.state.predictor
    try:
        resultado = processar_telemetria(db, payload.model_dump(), predictor)
    except Exception:
        logging.exception("Erro ao processar telemetria")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao processar telemetria")

    log(
        db,
        id_usuario=user["id_usuario"],
        acao="receber_telemetria",
        recurso="/api/v1/telemetria",
        id_equipamento=payload.id_equipamento,
        id_registro=resultado["id_registro"],
        detalhes=f"score_regra={resultado['score_risco']}; predito={resultado['nivel_risco_predito']}",
        ip_origem=_get_client_ip(request),
    )
    return resultado
