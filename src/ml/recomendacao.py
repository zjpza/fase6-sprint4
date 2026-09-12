from __future__ import annotations

import json


RECOMENDACOES = {
    "Crítico": "🚨 Risco crítico detectado. Suspender a operação imediatamente e acionar o gestor de frota.",
    "Alto": "⚠️ Risco alto. Reduzir velocidade, evitar áreas alagadiças e monitorar condições do solo.",
    "Médio": "⚡ Atenção moderada. Acompanhar evolução do clima e do terreno.",
    "Baixo": "✅ Operação dentro de parâmetros seguros.",
}

ROTULOS_FRIENDLY = {
    "umidade_solo_pct": "umidade do solo",
    "proximidade_agua_m": "proximidade de corpos d'água",
    "precipitacao_mm": "precipitação recente",
    "declividade_graus": "declividade do terreno",
    "velocidade_operacao_kmh": "velocidade de operação",
    "carga_pct": "percentual de carga",
    "horas_uso_equipamento": "horas de uso do equipamento",
    "dias_ultima_manutencao": "dias desde última manutenção",
    "historico_incidentes": "histórico de incidentes",
    "velocidade_vento_kmh": "velocidade do vento",
    "temperatura_c": "temperatura ambiente",
    "visibilidade_m": "visibilidade",
    "tipo_solo_encoded": "tipo de solo",
    "tipo_operacao_encoded": "tipo de operação",
}


def recomendar(nivel_risco: str, fatores: list[str] | str | None = None) -> str:
    """Retorna uma recomendação textual amigável para o operador/gestor."""
    base = RECOMENDACOES.get(nivel_risco, "Consulte o gestor de frota.")

    if fatores is None:
        return base

    if isinstance(fatores, str):
        try:
            fatores = json.loads(fatores)
        except json.JSONDecodeError:
            fatores = [fatores]

    if fatores:
        traduzidos = [ROTULOS_FRIENDLY.get(f, f) for f in fatores]
        base += f" Fatores principais: {', '.join(traduzidos)}."

    return base


def mensagem_alerta(
    nivel_regra: str,
    componentes: dict[str, float],
    pred: dict | None = None,
) -> str:
    """Mensagem do alerta: a regra decide e explica; o modelo aparece como segunda opinião.

    `pred` (opcional) traz {"nivel_risco_predito": str, "score_risco_predito": int}.
    Níveis divergentes sinalizam caso ambíguo em vez de decidirem o alerta.
    """
    top = sorted(componentes.items(), key=lambda par: par[1], reverse=True)[:3]
    fatores = [f"{nome} ({pontos:.0f} pts)" for nome, pontos in top]
    mensagem = recomendar(nivel_regra, fatores)
    if pred and pred.get("nivel_risco_predito") and pred["nivel_risco_predito"] != nivel_regra:
        mensagem += (
            f" Segunda opinião do modelo: {pred['nivel_risco_predito']} "
            f"({pred.get('score_risco_predito', '—')}) — caso divergente, inspecione as "
            "condições antes de confiar."
        )
    return mensagem