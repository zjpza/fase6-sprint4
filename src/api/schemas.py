from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TelemetriaInput(BaseModel):
    id_equipamento: str
    tipo_operacao: str = Field(..., pattern="^(Campo|Transporte)$")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    proximidade_agua_m: int = Field(..., ge=0)
    precipitacao_mm: float = Field(..., ge=0)
    umidade_solo_pct: float = Field(..., ge=0, le=100)
    tipo_solo: str = Field(..., pattern="^(Argiloso|Arenoso|Misto)$")
    declividade_graus: float = Field(..., ge=0)
    temperatura_c: float
    velocidade_vento_kmh: float = Field(..., ge=0)
    visibilidade_m: int = Field(..., ge=0)
    horas_uso_equipamento: int = Field(..., ge=0)
    dias_ultima_manutencao: int = Field(..., ge=0)
    velocidade_operacao_kmh: float = Field(..., ge=0)
    carga_pct: float = Field(..., ge=0, le=100)
    nivel_combustivel_pct: float = Field(..., ge=0, le=100)
    historico_incidentes: int = Field(..., ge=0)

    @field_validator("tipo_operacao", "tipo_solo", mode="before")
    @classmethod
    def strip_strings(cls, v: str) -> str:
        return v.strip()


class TelemetriaResponse(BaseModel):
    id_registro: int
    id_equipamento: str
    score_risco: int
    nivel_risco: str
    alerta_gerado: bool
    score_risco_predito: int
    nivel_risco_predito: str
    alerta_predito: bool
    recomendacao: str
    fatores_principais: list[str]
    data_hora: datetime


class EquipamentoResponse(BaseModel):
    id_equipamento: str
    tipo_equipamento: str
    estado_uf: str
    latitude_base: float | None
    longitude_base: float | None


class AlertaResponse(BaseModel):
    id_alerta: int
    id_registro: int
    id_equipamento: str
    data_hora_alerta: datetime
    nivel_risco: str
    score_risco: int
    mensagem: str


class LoginInput(BaseModel):
    email: str
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id_usuario: int
    nome: str
    email: str
    role: str
    id_equipamento_acesso: str | None = None


class TelemetriaHistoricoResponse(BaseModel):
    id_registro: int
    id_equipamento: str
    data_hora: datetime
    latitude: float | None = None
    longitude: float | None = None
    tipo_operacao: str | None = None
    proximidade_agua_m: int | None = None
    precipitacao_mm: float | None = None
    umidade_solo_pct: float | None = None
    tipo_solo: str | None = None
    declividade_graus: float | None = None
    temperatura_c: float | None = None
    velocidade_vento_kmh: float | None = None
    visibilidade_m: int | None = None
    horas_uso_equipamento: int | None = None
    dias_ultima_manutencao: int | None = None
    velocidade_operacao_kmh: float | None = None
    carga_pct: float | None = None
    nivel_combustivel_pct: float | None = None
    historico_incidentes: int | None = None
    score_risco: int | None = None
    nivel_risco: str | None = None
    alerta_gerado: int | None = None
    tipo_equipamento: str | None = None
    estado_uf: str | None = None
    score_risco_predito: int | None = None
    nivel_risco_predito: str | None = None
    modelo_utilizado: str | None = None
