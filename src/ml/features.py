"""Features de risco — fonte unica de verdade compartilhada entre ETL e API.

Centraliza os mapeamentos (encoders), a faixa de proximidade de agua, a
classificacao de nivel de risco, o calculo de features por registro e o score
heuristico deterministico usado na inferencia. Tanto o pipeline de ETL
(``data.feature_engineering``) quanto a API (``api.telemetria_service``)
importam deste modulo, eliminando a duplicacao que poderia causar drift
silencioso entre o treino (Sprint 2) e a inferencia (Sprint 3).

Nota: ``generate_dataset.calcular_score`` e a funcao que rotulou o dataset de
treino (com ruido); ``score_regra`` aqui e a heuristica deterministica usada na
inferencia em tempo real — propositadamente distintas.
"""
from __future__ import annotations

SOLO_ENCODER = {"Arenoso": 0, "Misto": 1, "Argiloso": 2}
OPERACAO_ENCODER = {"Transporte": 0, "Campo": 1}
FAIXA_ENCODER = {"Baixo": 0, "Médio": 1, "Alto": 2, "Crítico": 3}


def faixa_proximidade(valor: int) -> str:
    if valor < 50:
        return "Crítico"
    if valor < 200:
        return "Alto"
    if valor < 500:
        return "Médio"
    return "Baixo"


def classificar_risco(score: int) -> str:
    if score <= 25:
        return "Baixo"
    if score <= 50:
        return "Médio"
    if score <= 75:
        return "Alto"
    return "Crítico"


def calcular_features(dados: dict) -> dict:
    """Adiciona as features derivadas esperadas pelo modelo a um dict de telemetria."""
    row = dict(dados)
    row["tipo_solo_encoded"] = SOLO_ENCODER[row["tipo_solo"]]
    row["tipo_operacao_encoded"] = OPERACAO_ENCODER[row["tipo_operacao"]]
    faixa = faixa_proximidade(row["proximidade_agua_m"])
    row["faixa_proximidade_agua"] = faixa
    row["faixa_proximidade_encoded"] = FAIXA_ENCODER[faixa]
    row["indice_desgaste"] = row["horas_uso_equipamento"] / max(row["dias_ultima_manutencao"], 1)
    row["risco_solo"] = (
        row["umidade_solo_pct"] * row["tipo_solo_encoded"]
    ) / max(row["declividade_graus"], 0.1)
    row["risco_atolamento"] = (
        row["faixa_proximidade_encoded"] * 25
        + row["umidade_solo_pct"] * 0.35
        + row["precipitacao_mm"] * 0.25
        + row["tipo_solo_encoded"] * 8
    )
    row["risco_operacional"] = (
        row["velocidade_operacao_kmh"] * (3 if row["tipo_operacao"] == "Campo" else 0.6)
        + row["carga_pct"] * 0.3
        + row["declividade_graus"] * 2
        + max(0, 1000 - row["visibilidade_m"]) * 0.02
    )
    row["risco_manutencao"] = (
        row["horas_uso_equipamento"] / 120
        + row["dias_ultima_manutencao"] * 0.35
        + row["historico_incidentes"] * 9
    )
    return row


def score_regra(row: dict) -> int:
    """Score de risco heuristico deterministico (inferencia em tempo real)."""
    score = 0
    score += max(0, 50 - row["proximidade_agua_m"] / 10)
    score += row["umidade_solo_pct"] * 0.25
    score += row["precipitacao_mm"] * 0.35
    score += row["tipo_solo_encoded"] * 5
    score += row["declividade_graus"] * 1.5
    score += row["velocidade_operacao_kmh"] * (1.2 if row["tipo_operacao"] == "Campo" else 0.2)
    score += row["carga_pct"] * 0.15
    score += row["historico_incidentes"] * 7
    score += max(0, row["dias_ultima_manutencao"] - 30) * 0.3
    score += max(0, row["horas_uso_equipamento"] - 3000) / 200
    score += max(0, 1000 - row["visibilidade_m"]) * 0.01
    return int(min(100, max(0, score)))