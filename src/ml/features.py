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

# Bandas oficiais do score 0-100. Fonte única do nível de risco: `classificar_risco`
# e o score contínuo (que usa o ponto médio de cada banda) saem daqui.
FAIXAS_NIVEL = {
    "Baixo": (0, 25),
    "Médio": (26, 50),
    "Alto": (51, 75),
    "Crítico": (76, 100),
}

# Ponto médio de cada banda — o "valor" de um nível dentro do score contínuo.
REPRESENTANTE_NIVEL = {
    nivel: (minimo + maximo) / 2 for nivel, (minimo, maximo) in FAIXAS_NIVEL.items()
}


def faixa_proximidade(valor: int) -> str:
    if valor < 50:
        return "Crítico"
    if valor < 200:
        return "Alto"
    if valor < 500:
        return "Médio"
    return "Baixo"


def classificar_risco(score: int) -> str:
    score = min(100, max(0, score))
    for nivel, (minimo, maximo) in FAIXAS_NIVEL.items():
        if minimo <= score <= maximo:
            return nivel
    return "Crítico"


def score_continuo(probabilidades: dict[str, float]) -> float:
    """Score 0-100 contínuo: esperança do nível, ponderada pelas probabilidades do modelo.

    Substitui o valor fixo por classe (Baixo=12, Médio=38, Alto=63, Crítico=88 da
    Sprint 3): dois registros classificados como "Alto" com confianças diferentes
    deixam de receber o mesmo score. O representante de cada faixa é o ponto médio
    da banda de `classificar_risco`, então o score devolvido continua caindo na
    faixa do nível predito quando esse nível domina as probabilidades.
    """
    return sum(
        probabilidade * REPRESENTANTE_NIVEL[nivel]
        for nivel, probabilidade in probabilidades.items()
        if nivel in REPRESENTANTE_NIVEL
    )


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


def componentes_regra(row: dict) -> dict[str, float]:
    """Penalidades nomeadas da regra — decomposição auditável de score_regra.

    As chaves são rótulos amigáveis (PT) usados na mensagem de alerta; os valores
    são os pontos que cada termo soma ao score. `score_regra` é a soma destes
    termos — fonte única da fórmula, sem duplicação.
    """
    return {
        "proximidade de água": max(0, 50 - row["proximidade_agua_m"] / 10),
        "umidade do solo": row["umidade_solo_pct"] * 0.25,
        "precipitação": row["precipitacao_mm"] * 0.35,
        "tipo de solo": row["tipo_solo_encoded"] * 5,
        "declividade": row["declividade_graus"] * 1.5,
        "velocidade de operação": row["velocidade_operacao_kmh"] * (1.2 if row["tipo_operacao"] == "Campo" else 0.2),
        "carga": row["carga_pct"] * 0.15,
        "histórico de incidentes": row["historico_incidentes"] * 7,
        "manutenção atrasada": max(0, row["dias_ultima_manutencao"] - 30) * 0.3,
        "horas de uso": max(0, row["horas_uso_equipamento"] - 3000) / 200,
        "visibilidade": max(0, 1000 - row["visibilidade_m"]) * 0.01,
    }


def score_regra(row: dict) -> int:
    """Score de risco heuristico deterministico (inferencia em tempo real)."""
    return int(min(100, max(0, sum(componentes_regra(row).values()))))