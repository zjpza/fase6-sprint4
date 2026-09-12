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

# Tentativas por registro em falha transitória (timeout, conexão, 5xx) e espera base
# do backoff exponencial.
TENTATIVAS = 3
ESPERA_BASE = 0.5

# Tamanho da faixa de ids de coleta por lote (separa ondas de coleta no mesmo banco).
LOTE_TAMANHO = 1_000_000

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


def _normalizar_base_url(base_url: str) -> str:
    """Normaliza a URL base para apontar ao prefixo da API (/api/v1).

    Aceita tanto ``http://host:porta`` quanto ``http://host:porta/api/v1`` —
    corrige o 404 de quem passou a raiz sem o prefixo (achado B3 da auditoria).
    """
    base = base_url.rstrip("/")
    if base.endswith("/api/v1"):
        return base
    return f"{base}/api/v1"


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


def _esperar_antes_da_proxima(tentativa: int, espera_base: float) -> None:
    """Espera do backoff exponencial entre tentativas (0 desliga a espera, útil em teste)."""
    time.sleep(espera_base * 2 ** (tentativa - 1))


def _login_com_retry(
    client: httpx.Client,
    base_url: str,
    credenciais: dict,
    tentativas: int = TENTATIVAS,
    espera_base: float = ESPERA_BASE,
) -> str:
    """Tenta autenticar algumas vezes e falha com mensagem clara se a API não responder."""
    motivo = "sem resposta"
    for tentativa in range(1, tentativas + 1):
        try:
            return _login(client, base_url, credenciais["email"], credenciais["senha"])
        except httpx.TransportError as exc:
            motivo = f"{type(exc).__name__}: {exc}"
        except httpx.HTTPStatusError as exc:
            motivo = f"HTTP {exc.response.status_code} no login"
        if tentativa < tentativas:
            _esperar_antes_da_proxima(tentativa, espera_base)

    raise SystemExit(f"API inacessível em {base_url} — {motivo}")


def _id_da_coleta(id_registro: int, lote: int = 0) -> int:
    """Id da coleta enviado à API: o lote desloca a faixa para simular ondas de coleta distintas."""
    return lote * LOTE_TAMANHO + int(id_registro)


def _montar_payload(row: dict, lote: int = 0) -> dict:
    """Mapeia uma linha do dataset para o payload TelemetriaInput, com o id da coleta."""
    payload = {field: row[field] for field in PAYLOAD_FIELDS}
    # O id da linha do dataset identifica a coleta: reenviar o mesmo registro (mesmo lote)
    # devolve 409 em vez de gravar duas vezes a mesma medição (rastreabilidade da #3).
    payload["id_coleta"] = _id_da_coleta(row["id_registro"], lote)
    return payload


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


def _selecionar_registros(n: int, equipamento: str | None = None) -> list[dict]:
    """Primeiros `n` registros do dataset determinístico.

    Com ``equipamento``, os registros são enviados **como se viessem desse equipamento**
    — é o que permite demonstrar a visão do operador (que só pode postar do próprio
    equipamento) sem depender de o dataset sortear justamente aquele id.
    """
    pool = gerar_dataset(max(n, 500))
    registros = pool.head(n).to_dict(orient="records")
    if equipamento:
        for registro in registros:
            registro["id_equipamento"] = equipamento
    return registros


def _enviar_com_retry(
    client: httpx.Client,
    base_url: str,
    credenciais: dict,
    payload: dict,
    token: str,
    tentativas: int = TENTATIVAS,
    espera_base: float = ESPERA_BASE,
) -> tuple[httpx.Response | None, str, str]:
    """Envia um registro, repetindo falhas transitórias (timeout, conexão, 5xx).

    Devolve a resposta final (ou ``None``), o token atualizado e o motivo da falha.
    Token expirado (401) renova o login e reenvia; falha de rede/5xx espera e tenta
    de novo — o registro não é descartado em silêncio.
    """
    motivo = "sem resposta após as tentativas"
    for tentativa in range(1, tentativas + 1):
        try:
            resp = _postar_telemetria(client, base_url, token, payload)
        except httpx.TransportError as exc:
            motivo = f"{type(exc).__name__}: {exc}"
            if tentativa < tentativas:
                _esperar_antes_da_proxima(tentativa, espera_base)
            continue

        if resp.status_code == 401:  # token expirado: re-login e reenvia
            token = _login(client, base_url, credenciais["email"], credenciais["senha"])
            motivo = "não autorizado após re-login"
            continue

        if resp.status_code >= 500:
            motivo = f"HTTP {resp.status_code}"
            if tentativa < tentativas:
                _esperar_antes_da_proxima(tentativa, espera_base)
            continue

        return resp, token, ""

    return None, token, motivo


def _imprimir_resultado(resp: httpx.Response, id_equipamento: str) -> None:
    """Imprime a linha de saída: EQ-... -> score (nivel) | predito (nivel) | alerta SIM/NÃO | divergente."""
    data = resp.json()
    alerta = "SIM" if data.get("alerta_gerado") else "NÃO"
    divergente = " | divergente" if data.get("divergente") else ""
    print(
        f"{id_equipamento} -> {data['score_risco']} ({data['nivel_risco']}) | "
        f"predito {data['score_risco_predito']} ({data['nivel_risco_predito']}) | "
        f"alerta {alerta}{divergente}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de telemetria AgroRisk AI")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1", help="URL base da API")
    parser.add_argument("--n", type=int, default=20, help="Número de registros a enviar")
    parser.add_argument("--interval", type=float, default=2.0, help="Intervalo entre envios (segundos)")
    parser.add_argument("--role", default="gestor", choices=list(CREDENCIAIS), help="Papel para autenticação")
    parser.add_argument(
        "--equipamento",
        default=None,
        help="Envia os registros como se viessem deste equipamento (use com --role operador)",
    )
    parser.add_argument(
        "--lote",
        type=int,
        default=0,
        help="Identificador do lote de coleta: mude para reenviar as mesmas medições como coleta nova",
    )
    args = parser.parse_args()

    base_url = _normalizar_base_url(args.base_url)
    cred = CREDENCIAIS[args.role]
    registros = _selecionar_registros(args.n, args.equipamento)

    enviados = aceitos = duplicados = rejeitados = falhas = 0
    with httpx.Client(timeout=30.0) as client:
        token = _login_com_retry(client, base_url, cred)

        for i, row in enumerate(registros):
            payload = _montar_payload(row, args.lote)
            id_eq = payload["id_equipamento"]
            enviados += 1

            resp, token, motivo = _enviar_com_retry(client, base_url, cred, payload, token)

            if resp is None:
                falhas += 1
                print(f"{id_eq} -> FALHA após {TENTATIVAS} tentativas ({motivo})")
            elif resp.status_code == 201:
                aceitos += 1
                _imprimir_resultado(resp, id_eq)
            elif resp.status_code == 409:
                duplicados += 1
                print(f"{id_eq} -> coleta já registrada ({resp.json().get('detail')})")
            else:
                rejeitados += 1
                print(f"{id_eq} -> ERRO HTTP {resp.status_code}: {resp.text}")

            if i < len(registros) - 1:
                time.sleep(args.interval)

    print(
        f"\nResumo: {enviados} enviados | {aceitos} aceitos | {duplicados} já registrados | "
        f"{rejeitados} rejeitados pela API | {falhas} falhas de rede"
    )
    if rejeitados or falhas:
        raise SystemExit(1)


if __name__ == "__main__":
    main()