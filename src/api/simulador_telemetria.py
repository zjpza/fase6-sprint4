"""Simulador de telemetria em fluxo contínuo para demonstração da API AgroRisk AI.

Envia registros de telemetria gerados sinteticamente (gerar_dataset, SEED=42) para o
endpoint POST /api/v1/telemetria, autenticando-se previamente via POST /api/v1/login.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

# Bootstrap de path para permitir `from data.generate_dataset import gerar_dataset`.
SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.generate_dataset import gerar_dataset

# Mapeamento role → credenciais de demonstração.
CREDENCIAIS = {
    "operador": {"email": "carlos@agrorisk.local", "senha": "operador123"},
    "gestor": {"email": "fernanda@agrorisk.local", "senha": "gestor123"},
}

# Campos do payload TelemetriaInput na ordem esperada pela API.
PAYLOAD_FIELDS = [
    "id_equipamento",
    "tipo_operacao",
    "latitude",
    "longitude",
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
]


def _login(client: httpx.Client, base_url: str, email: str, senha: str) -> str:
    """Autentica na API e retorna o access_token."""
    resp = client.post(
        f"{base_url}/login",
        json={"email": email, "senha": senha},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _montar_payload(row: dict) -> dict:
    """Mapeia uma linha do dataset para o payload TelemetriaInput."""
    return {field: row[field] for field in PAYLOAD_FIELDS}


def _postar_telemetria(
    client: httpx.Client,
    base_url: str,
    token: str,
    payload: dict,
) -> httpx.Response:
    """Envia um registro de telemetria autenticado."""
    return client.post(
        f"{base_url}/telemetria",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _imprimir_resultado(resp: httpx.Response, id_equipamento: str) -> None:
    """Imprime a linha de saída no formato: EQ-... -> score (nivel) | predito (nivel) | alerta SIM/NÃO."""
    data = resp.json()
    alerta = "SIM" if data.get("alerta_predito") else "NÃO"
    print(
        f"{id_equipamento} -> {data['score_risco']} ({data['nivel_risco']}) | "
        f"predito {data['score_risco_predito']} ({data['nivel_risco_predito']}) | "
        f"alerta {alerta}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de telemetria AgroRisk AI")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1", help="URL base da API")
    parser.add_argument("--n", type=int, default=20, help="Número de registros a enviar")
    parser.add_argument("--interval", type=float, default=2.0, help="Intervalo entre envios (segundos)")
    parser.add_argument("--role", default="gestor", choices=list(CREDENCIAIS), help="Papel para autenticação")
    args = parser.parse_args()

    cred = CREDENCIAIS[args.role]

    # Constrói o pool de registros a partir do dataset determinístico (SEED=42).
    # gerar_dataset valida que o dataset tenha >= 500 registros; geramos o mínimo
    # aceito e enviamos apenas os primeiros --n.
    pool_size = max(args.n, 500)
    df = gerar_dataset(pool_size).head(args.n)
    registros = df.to_dict(orient="records")

    with httpx.Client(timeout=30.0) as client:
        token = _login(client, args.base_url, cred["email"], cred["senha"])

        for i, row in enumerate(registros):
            payload = _montar_payload(row)
            id_eq = payload["id_equipamento"]

            resp = _postar_telemetria(client, args.base_url, token, payload)

            if resp.status_code == 401:
                # Token expirado — re-login e retry uma vez.
                token = _login(client, args.base_url, cred["email"], cred["senha"])
                resp = _postar_telemetria(client, args.base_url, token, payload)

            if resp.status_code == 201:
                _imprimir_resultado(resp, id_eq)
            else:
                print(f"{id_eq} -> ERRO HTTP {resp.status_code}: {resp.text}")

            if i < len(registros) - 1:
                time.sleep(args.interval)


if __name__ == "__main__":
    main()