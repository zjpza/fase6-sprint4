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
