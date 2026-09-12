from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TelemetriaInput(BaseModel):
    id_equipamento: str
    id_coleta: int | None = Field(
        None,
        ge=0,
        description=(
            "Identificador da coleta na fonte (opcional). Quando informado, a mesma coleta "
            "não é registrada duas vezes: repetir o envio devolve 409 com o registro existente."
        ),
    )
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
    score_risco: int = Field(
        ...,
        description="Score 0-100 da regra explícita do domínio (heurística determinística, auditável linha a linha).",
    )
    nivel_risco: str = Field(..., description="Nível derivado do score da regra (Baixo/Médio/Alto/Crítico).")
    alerta_gerado: bool = Field(
        ...,
        description="Alerta emitido pela decisão da REGRA (fonte única de decisão do sistema).",
    )
    score_risco_predito: int = Field(
        ...,
        description=(
            "Score 0-100 do modelo Random Forest, contínuo: média das faixas ponderada pelas "
            "probabilidades previstas. Mesma escala do score_risco, então os dois são comparáveis."
        ),
    )
    nivel_risco_predito: str = Field(..., description="Classe prevista pelo modelo (argumento de maior probabilidade).")
    alerta_predito: bool = Field(
        ...,
        description="O modelo também vê Alto/Crítico? Segunda opinião — não decide o alerta.",
    )
    divergente: bool = Field(
        ...,
        description="Regra e modelo classificam em níveis diferentes — caso ambíguo sinalizado ao operador.",
    )
    recomendacao: str
    fatores_principais: list[str] = Field(
        ...,
        description="Variáveis que mais mudam a probabilidade do nível previsto neste registro (ordem de contribuição).",
    )
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
    tipo_alerta: str | None = Field(
        None, description="Preventivo (Alto) ou Crítico — o dashboard usa para separar a leitura."
    )
    lido: int | None = Field(None, description="0 = não lido pelo operador, 1 = lido.")


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


class AuditoriaResponse(BaseModel):
    id_auditoria: int
    data_hora: datetime
    usuario: str | None = Field(None, description="Nome de quem fez a chamada (nulo para chamadas sem usuário).")
    acao: str = Field(..., description="O que aconteceu (login, telemetria, decisao_risco, consultas).")
    recurso: str | None = None
    id_equipamento: str | None = None
    id_registro: int | None = None
    detalhes: str | None = Field(
        None,
        description="Contexto da chamada; nas decisões de risco traz score da regra, score do modelo, alerta e fatores.",
    )
    ip_origem: str | None = None


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
    fatores_principais: list[str] = Field(
        default_factory=list,
        description="Variáveis que mais pesaram na predição deste registro.",
    )
