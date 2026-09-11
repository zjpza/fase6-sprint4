"""Cliente exemplo para demonstrar o fluxo ponta a ponta da Sprint 3.

1. Faz login como operador.
2. Envia um registro de telemetria.
3. Recebe score, nível de risco, alerta e recomendação.
4. Consulta equipamentos e alertas como gestor.
"""
from __future__ import annotations

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"

CREDENTIALS = {
    "operador": {"email": "carlos@agrorisk.local", "senha": "operador123"},
    "gestor": {"email": "fernanda@agrorisk.local", "senha": "gestor123"},
}

TELEMETRIA_EXEMPLO = {
    "id_equipamento": "EQ-MT-0023",
    "tipo_operacao": "Campo",
    "latitude": -13.4295,
    "longitude": -56.7891,
    "proximidade_agua_m": 120,
    "precipitacao_mm": 45.2,
    "umidade_solo_pct": 78.5,
    "tipo_solo": "Argiloso",
    "declividade_graus": 12.3,
    "temperatura_c": 32.1,
    "velocidade_vento_kmh": 28.0,
    "visibilidade_m": 800,
    "horas_uso_equipamento": 3420,
    "dias_ultima_manutencao": 45,
    "velocidade_operacao_kmh": 8.5,
    "carga_pct": 92.0,
    "nivel_combustivel_pct": 35.0,
    "historico_incidentes": 2,
}


def login(role: str) -> str:
    r = httpx.post(f"{BASE_URL}/login", json=CREDENTIALS[role])
    r.raise_for_status()
    return r.json()["access_token"]


def enviar_telemetria(token: str) -> dict:
    r = httpx.post(
        f"{BASE_URL}/telemetria",
        json=TELEMETRIA_EXEMPLO,
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()


def listar_alertas(token: str) -> list:
    r = httpx.get(f"{BASE_URL}/alertas", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def main() -> None:
    print("=" * 60)
    print("AgroRisk AI - Pipeline Client - Sprint 3")
    print("=" * 60)

    token_op = login("operador")
    print("\n[1] Login como Operador: OK")

    resultado = enviar_telemetria(token_op)
    print(f"\n[2] Telemetria enviada para {resultado['id_equipamento']}")
    print(f"    Score de risco (regra): {resultado['score_risco']} ({resultado['nivel_risco']})")
    print(f"    Score predito (ML): {resultado['score_risco_predito']} ({resultado['nivel_risco_predito']})")
    print(f"    Alerta: {'SIM' if resultado['alerta_predito'] else 'NÃO'}")
    print(f"    Recomendação: {resultado['recomendacao']}")

    token_gestor = login("gestor")
    alertas = listar_alertas(token_gestor)
    print(f"\n[3] Login como Gestor: OK")
    print(f"    Total de alertas: {len(alertas)}")
    if alertas:
        ultimo = alertas[0]
        print(f"    Último alerta: {ultimo['mensagem']}")

    print("\n[4] Fluxo ponta a ponta concluído com sucesso.")
    print("=" * 60)


if __name__ == "__main__":
    main()
