"""Higienização da telemetria antes da carga no banco (issue #3).

A carga não pode confiar no CSV: `INSERT` de uma linha faltante ou incoerente
morre no meio do `executemany` (constraint/trigger) e deixa a base pela metade.
Aqui os problemas são classificados, as linhas ruins saem com motivo registrado
e só o que é íntegro segue para consumo do modelo.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# Coluna de rastreabilidade: sem ela não há como registrar de qual coleta a linha veio.
COLUNAS_RASTREABILIDADE = ("id_registro",)

# Colunas que o modelo e o score consomem — sem elas a linha não serve.
# Espelha os campos obrigatórios de `src/sql/01_schema.sql`.
COLUNAS_OBRIGATORIAS = (
    "id_equipamento",
    "data_hora",
    "tipo_operacao",
    "proximidade_agua_m",
    "precipitacao_mm",
    "umidade_solo_pct",
    "tipo_solo",
    "declividade_graus",
    "temperatura_c",
    "velocidade_vento_kmh",
    "visibilidade_m",
    "horas_uso_equipamento",
    "dias_ultima_manutencao",
    "velocidade_operacao_kmh",
    "carga_pct",
    "nivel_combustivel_pct",
    "historico_incidentes",
    "score_risco",
    "nivel_risco",
    "alerta_gerado",
)

# Colunas convertidas para numérico antes de qualquer checagem de valor.
COLUNAS_NUMERICAS = tuple(
    coluna
    for coluna in COLUNAS_OBRIGATORIAS
    if coluna not in ("id_equipamento", "data_hora", "tipo_operacao", "tipo_solo", "nivel_risco", "alerta_gerado")
) + ("score_risco_calculado",)

# Domínios fechados, idênticos aos CHECK do schema.
DOMINIOS = {
    "tipo_operacao": ("Campo", "Transporte"),
    "tipo_solo": ("Argiloso", "Arenoso", "Misto"),
    "nivel_risco": ("Baixo", "Médio", "Alto", "Crítico"),
}

# Faixas físicas/contratuais (limite inferior, superior; None = sem limite).
RANGES = {
    "score_risco": (0, 100),
    "score_risco_calculado": (0, 100),
    "umidade_solo_pct": (0, 100),
    "carga_pct": (0, 100),
    "nivel_combustivel_pct": (0, 100),
    "declividade_graus": (0, 90),
    "precipitacao_mm": (0, None),
    "proximidade_agua_m": (0, None),
    "visibilidade_m": (0, None),
    "horas_uso_equipamento": (0, None),
    "dias_ultima_manutencao": (0, None),
    "historico_incidentes": (0, None),
    "velocidade_vento_kmh": (0, None),
    "velocidade_operacao_kmh": (0, None),
    "temperatura_c": (-20, 60),
    "latitude": (-90, 90),
    "longitude": (-180, 180),
}

MOTIVOS = ("faltante", "duplicado", "dominio_invalido", "fora_de_range", "inconsistente")

# Chave natural de uma coleta: mesma máquina no mesmo instante é o mesmo registro.
CHAVE_NATURAL = ("id_equipamento", "data_hora")

_FORMATO_DATA_HORA = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class RelatorioHigiene:
    """Quantas linhas entraram na higienização e quantas saíram descartadas, por motivo."""

    total_entrada: int
    descartados: dict[str, int] = field(default_factory=dict)

    @property
    def total_descartados(self) -> int:
        return sum(self.descartados.values())

    @property
    def total_aproveitado(self) -> int:
        return self.total_entrada - self.total_descartados


def _para_booleano(valor: object) -> bool | None:
    """Converte as representações de alerta aceitas na fonte; inválido vira None (faltante)."""
    if isinstance(valor, bool):
        return valor
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or pd.isna(valor):
        return None
    if isinstance(valor, (int, float)):
        return bool(valor)
    texto = str(valor).strip().lower()
    if texto in {"true", "1", "sim"}:
        return True
    if texto in {"false", "0", "não", "nao"}:
        return False
    return None


def higienizar(df: pd.DataFrame) -> tuple[pd.DataFrame, RelatorioHigiene]:
    """Descartar (com motivo) as linhas que não podem entrar no banco.

    Falha com ``ValueError`` se faltar coluna obrigatória estrutural: isso é
    contrato quebrado da fonte, não linha suja — não há como adivinhar.
    """
    ausentes = [
        coluna
        for coluna in (*COLUNAS_OBRIGATORIAS, *COLUNAS_RASTREABILIDADE)
        if coluna not in df.columns
    ]
    if ausentes:
        raise ValueError(f"Fonte sem colunas obrigatórias: {', '.join(ausentes)}")

    dados = df.copy()
    descartados = dict.fromkeys(MOTIVOS, 0)

    for coluna in (*COLUNAS_NUMERICAS, *COLUNAS_RASTREABILIDADE):
        if coluna in dados.columns:
            dados[coluna] = pd.to_numeric(dados[coluna], errors="coerce")
    dados["data_hora"] = pd.to_datetime(dados["data_hora"], errors="coerce")
    dados["alerta_gerado"] = dados["alerta_gerado"].map(_para_booleano)

    def descartar(motivo: str, mascara: pd.Series) -> None:
        nonlocal dados
        quantidade = int(mascara.sum())
        if quantidade:
            descartados[motivo] += quantidade
            dados = dados[~mascara]

    obrigatorias = [*COLUNAS_OBRIGATORIAS, *COLUNAS_RASTREABILIDADE]
    descartar("faltante", dados[obrigatorias].isna().any(axis=1))
    descartar("duplicado", dados.duplicated(subset=list(CHAVE_NATURAL), keep="first"))

    invalido = pd.Series(False, index=dados.index)
    for coluna, permitidos in DOMINIOS.items():
        invalido |= ~dados[coluna].isin(permitidos)
    descartar("dominio_invalido", invalido)

    fora_de_range = pd.Series(False, index=dados.index)
    for coluna, (minimo, maximo) in RANGES.items():
        if coluna not in dados.columns:
            continue
        if minimo is not None:
            fora_de_range |= dados[coluna] < minimo
        if maximo is not None:
            fora_de_range |= dados[coluna] > maximo
    descartar("fora_de_range", fora_de_range)

    # Mesma regra do gatilho trg_valida_alerta: alerta só para Alto/Crítico.
    exige_alerta = dados["nivel_risco"].isin(("Alto", "Crítico"))
    descartar("inconsistente", exige_alerta != dados["alerta_gerado"])

    dados["data_hora"] = dados["data_hora"].dt.strftime(_FORMATO_DATA_HORA)
    dados["id_registro"] = dados["id_registro"].astype(int)
    return dados.reset_index(drop=True), RelatorioHigiene(
        total_entrada=len(df), descartados=descartados
    )
