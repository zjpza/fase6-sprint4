"""Testes das funções puras de features/score (fonte única: ml.features) e da inferência."""
from __future__ import annotations

import json

import httpx
import pandas as pd
import pytest

from api.simulador_telemetria import (
    _enviar_com_retry,
    _montar_payload,
    _selecionar_registros,
)
from ml.features import (
    FAIXAS_NIVEL as _FAIXAS_NIVEL,
    REPRESENTANTE_NIVEL as _REPRESENTANTE_NIVEL,
    calcular_features as _calcular_features,
    classificar_risco as _classificar_risco,
    faixa_proximidade as _faixa_proximidade,
    score_continuo as _score_continuo,
    score_regra as _score_regra,
)


def test_faixa_proximidade():
    assert _faixa_proximidade(10) == "Crítico"
    assert _faixa_proximidade(49) == "Crítico"
    assert _faixa_proximidade(50) == "Alto"
    assert _faixa_proximidade(199) == "Alto"
    assert _faixa_proximidade(200) == "Médio"
    assert _faixa_proximidade(499) == "Médio"
    assert _faixa_proximidade(500) == "Baixo"


def test_classificar_risco():
    assert _classificar_risco(0) == "Baixo"
    assert _classificar_risco(25) == "Baixo"
    assert _classificar_risco(26) == "Médio"
    assert _classificar_risco(50) == "Médio"
    assert _classificar_risco(51) == "Alto"
    assert _classificar_risco(75) == "Alto"
    assert _classificar_risco(76) == "Crítico"
    assert _classificar_risco(100) == "Crítico"


def test_score_continuo_pondera_as_probabilidades():
    """O score deixa de ser fixo por classe: a confiança do modelo muda o valor dentro da mesma faixa."""
    assert _score_continuo({"Alto": 1.0}) == pytest.approx(_REPRESENTANTE_NIVEL["Alto"])
    assert _score_continuo({"Crítico": 1.0}) > _score_continuo({"Alto": 1.0}) > _score_continuo({"Médio": 1.0})

    forte = _score_continuo({"Alto": 0.9, "Médio": 0.1})
    fraca = _score_continuo({"Alto": 0.5, "Médio": 0.5})
    assert forte != fraca
    assert _FAIXAS_NIVEL["Alto"][0] <= forte <= _FAIXAS_NIVEL["Alto"][1]


def test_representante_de_cada_nivel_fica_dentro_da_propria_faixa():
    """Score contínuo e nível predito falam a mesma língua: o valor de cada nível mora na sua banda."""
    for nivel, (minimo, maximo) in _FAIXAS_NIVEL.items():
        assert minimo <= _REPRESENTANTE_NIVEL[nivel] <= maximo


def _payload_alto():
    return {
        "proximidade_agua_m": 30,
        "umidade_solo_pct": 90,
        "precipitacao_mm": 50,
        "tipo_solo": "Argiloso",
        "declividade_graus": 15,
        "velocidade_operacao_kmh": 10,
        "carga_pct": 95,
        "historico_incidentes": 3,
        "dias_ultima_manutencao": 60,
        "horas_uso_equipamento": 5000,
        "visibilidade_m": 200,
        "tipo_operacao": "Campo",
    }


def test_score_regra_basico():
    row = _calcular_features(_payload_alto())
    score = _score_regra(row)
    assert 0 <= score <= 100
    assert score >= 70


def test_score_regra_baixo():
    payload = {
        "proximidade_agua_m": 800,
        "umidade_solo_pct": 20,
        "precipitacao_mm": 0,
        "tipo_solo": "Arenoso",
        "declividade_graus": 2,
        "velocidade_operacao_kmh": 5,
        "carga_pct": 30,
        "historico_incidentes": 0,
        "dias_ultima_manutencao": 5,
        "horas_uso_equipamento": 500,
        "visibilidade_m": 5000,
        "tipo_operacao": "Transporte",
    }
    row = _calcular_features(payload)
    score = _score_regra(row)
    assert 0 <= score <= 100
    assert score <= 25


def test_calcular_features_campos():
    row = _calcular_features(_payload_alto())
    for chave in (
        "tipo_solo_encoded",
        "tipo_operacao_encoded",
        "faixa_proximidade_agua",
        "faixa_proximidade_encoded",
        "indice_desgaste",
        "risco_solo",
        "risco_atolamento",
        "risco_operacional",
        "risco_manutencao",
    ):
        assert chave in row


class _RespostaFalsa:
    """Resposta httpx mínima para exercitar o retry do simulador."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=None)  # type: ignore[arg-type]


class _ClienteFalso:
    """Cliente httpx de mentira: entrega respostas/exceções na ordem programada."""

    def __init__(self, comportamentos: list) -> None:
        self._comportamentos = list(comportamentos)
        self.chamadas: list[str] = []

    def post(self, url: str, **_kwargs) -> "_RespostaFalsa":
        self.chamadas.append(url)
        comportamento = self._comportamentos.pop(0)
        if isinstance(comportamento, Exception):
            raise comportamento
        return comportamento


CREDENCIAIS_TESTE = {"email": "gestor@teste.local", "senha": "senha"}
PAYLOAD_TESTE = {"id_equipamento": "EQ-MT-0023", "id_coleta": 1}


def test_simulador_repete_falha_transitoria():
    """5xx é transitório: o registro é reenviado em vez de se perder."""
    cliente = _ClienteFalso([_RespostaFalsa(500), _RespostaFalsa(201, {"id_registro": 1})])

    resposta, _token, motivo = _enviar_com_retry(
        cliente, "http://api", CREDENCIAIS_TESTE, PAYLOAD_TESTE, "token", espera_base=0
    )

    assert (resposta.status_code, motivo) == (201, "")
    assert len(cliente.chamadas) == 2


def test_simulador_repete_timeout_de_conexao():
    """Falha de rede também é repetida antes de desistir."""
    cliente = _ClienteFalso([httpx.ConnectTimeout("timeout"), _RespostaFalsa(201, {"id_registro": 2})])

    resposta, _token, motivo = _enviar_com_retry(
        cliente, "http://api", CREDENCIAIS_TESTE, PAYLOAD_TESTE, "token", espera_base=0
    )

    assert (resposta.status_code, motivo) == (201, "")
    assert len(cliente.chamadas) == 2


def test_simulador_desiste_apos_as_tentativas_e_reporta():
    """Sem resposta depois das tentativas, a falha é reportada — não vira sucesso silencioso."""
    cliente = _ClienteFalso([_RespostaFalsa(503), _RespostaFalsa(503), _RespostaFalsa(503)])

    resposta, _token, motivo = _enviar_com_retry(
        cliente, "http://api", CREDENCIAIS_TESTE, PAYLOAD_TESTE, "token", espera_base=0
    )

    assert resposta is None
    assert "503" in motivo
    assert len(cliente.chamadas) == 3


def test_simulador_renova_token_expirado():
    """401 renova o login e reenvia o mesmo registro."""
    cliente = _ClienteFalso(
        [
            _RespostaFalsa(401),
            _RespostaFalsa(200, {"access_token": "novo-token"}),
            _RespostaFalsa(201, {"id_registro": 3}),
        ]
    )

    resposta, token, motivo = _enviar_com_retry(
        cliente, "http://api", CREDENCIAIS_TESTE, PAYLOAD_TESTE, "token-velho", espera_base=0
    )

    assert (resposta.status_code, token, motivo) == (201, "novo-token", "")
    assert cliente.chamadas[1].endswith("/login")


def test_simulador_envia_id_da_coleta_no_payload():
    """O payload carrega o id da coleta para o reenvio ser reconhecido pela API."""
    registros = _selecionar_registros(1, None)

    payload = _montar_payload(registros[0])

    assert payload["id_coleta"] == registros[0]["id_registro"]


def test_lote_desloca_o_id_da_coleta():
    """Lotes diferentes geram coletas diferentes para as mesmas medições."""
    registros = _selecionar_registros(1, None)

    primeiro = _montar_payload(registros[0], lote=0)["id_coleta"]
    segundo = _montar_payload(registros[0], lote=1)["id_coleta"]

    assert segundo != primeiro
    assert segundo > primeiro


def test_simulador_envia_no_equipamento_informado():
    """--equipamento permite ao operador coletar para o próprio equipamento (que o dataset pode não sortear)."""
    registros = _selecionar_registros(5, "EQ-MT-0023")

    assert len(registros) == 5
    assert {registro["id_equipamento"] for registro in registros} == {"EQ-MT-0023"}


# --- Sprint 4 (#2 REFACT): correções da auditoria (B3, B4, validações) ---

def test_normalizar_base_url_simulador():
    """B3: --base-url sem /api/v1 não pode mais gerar 404 no simulador."""
    from api.simulador_telemetria import _normalizar_base_url

    assert _normalizar_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000/api/v1"
    assert _normalizar_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/api/v1"
    assert _normalizar_base_url("http://127.0.0.1:8000/api/v1") == "http://127.0.0.1:8000/api/v1"
    assert _normalizar_base_url("http://127.0.0.1:8000/api/v1/") == "http://127.0.0.1:8000/api/v1"


def test_pipeline_importavel_como_pacote():
    """B4: ETL deve importar como pacote a partir de src/, sem depender de cwd=src/data."""
    import data.pipeline as pipeline

    assert callable(pipeline.executar_schema)
    assert callable(pipeline.run_pipeline)


def test_validar_features_mensagem_de_erro_clara():
    """Validação de features deve levantar ValueError com o problema nomeado, não assert genérico."""
    from data.feature_engineering import validar_features

    df = pd.DataFrame({"score_risco": [150], "diff_score": [0]})
    with pytest.raises(ValueError, match="score_risco"):
        validar_features(df)


# --- Sprint 4 (#4 ML): score contínuo e fatores por contribuição real ---

# Linha real da base (EQ-GO-0006, 841 m da água) cujo risco vem de velocidade, desgaste e
# umidade do solo: serve para provar que a distância até a água não é listada como fator
# só por ser um número grande.
TELEMETRIA_LONGE_DA_AGUA = {
    "id_equipamento": "EQ-GO-0006",
    "tipo_operacao": "Campo",
    "latitude": -16.3364,
    "longitude": -49.6161,
    "proximidade_agua_m": 841,
    "precipitacao_mm": 4.5,
    "umidade_solo_pct": 48.8,
    "tipo_solo": "Argiloso",
    "declividade_graus": 11.5,
    "temperatura_c": 32.9,
    "velocidade_vento_kmh": 33.6,
    "visibilidade_m": 4544,
    "horas_uso_equipamento": 6054,
    "dias_ultima_manutencao": 40,
    "velocidade_operacao_kmh": 10.5,
    "carga_pct": 44.4,
    "nivel_combustivel_pct": 97.1,
    "historico_incidentes": 3,
}

TELEMETRIA_LONGE_DA_AGUA_COM_DESGASTE = {
    **TELEMETRIA_LONGE_DA_AGUA,
    "id_equipamento": "EQ-GO-0006",
    "latitude": -16.313,
    "longitude": -49.765,
    "proximidade_agua_m": 2316,
    "precipitacao_mm": 14.1,
    "umidade_solo_pct": 24.2,
    "tipo_solo": "Arenoso",
    "declividade_graus": 0.7,
    "temperatura_c": 31.8,
    "velocidade_vento_kmh": 54.3,
    "visibilidade_m": 3806,
    "horas_uso_equipamento": 6035,
    "dias_ultima_manutencao": 113,
    "velocidade_operacao_kmh": 8.3,
    "carga_pct": 35.7,
    "nivel_combustivel_pct": 43.3,
    "historico_incidentes": 2,
}


def _predizer(*telemetrias: dict) -> list[dict]:
    """Prediz como a API prediz: telemetria crua → features derivadas → modelo."""
    from ml.predictor import RiskPredictor

    df = pd.DataFrame([_calcular_features(t) for t in telemetrias])
    return RiskPredictor().predict(df).to_dict(orient="records")


def test_fatores_mostram_contribuicao_e_nao_valor_absoluto():
    """Distância até a água deixa de aparecer como fator quando não é ela que move a predição."""
    predicao = _predizer(TELEMETRIA_LONGE_DA_AGUA)[0]
    fatores = json.loads(predicao["fatores_principais"])

    assert fatores, "a predição precisa indicar o que pesou"
    assert "proximidade_agua_m" not in fatores
    assert "faixa_proximidade_encoded" not in fatores
    assert "velocidade_operacao_kmh" in fatores or "risco_manutencao" in fatores


def test_fatores_mudam_conforme_o_que_pesa_no_registro():
    """Duas linhas igualmente longe da água: a proximidade é fator onde influencia, e não é onde não influencia."""
    sem_peso = json.loads(_predizer(TELEMETRIA_LONGE_DA_AGUA)[0]["fatores_principais"])
    com_peso = json.loads(_predizer(TELEMETRIA_LONGE_DA_AGUA_COM_DESGASTE)[0]["fatores_principais"])

    assert "proximidade_agua_m" not in sem_peso, "valor grande por si só não faz a variável ser fator"
    assert "proximidade_agua_m" in com_peso
    assert sem_peso != com_peso


def test_score_do_modelo_e_continuo_dentro_do_mesmo_nivel():
    """Registros no mesmo nível deixam de receber o mesmo score fixo da Sprint 3 (Baixo=12 ... Crítico=88)."""
    telemetrias = [
        dict(
            TELEMETRIA_LONGE_DA_AGUA,
            dias_ultima_manutencao=dias,
            historico_incidentes=incidentes,
        )
        for dias, incidentes in [(5, 0), (20, 0), (40, 0), (60, 1), (80, 1), (95, 2), (110, 3), (120, 5)]
    ]
    predicoes = _predizer(*telemetrias)
    scores = [predicao["score_risco_predito"] for predicao in predicoes]

    assert len(set(scores)) > 4, "o mapa fixo por classe só produzia 4 valores"

    por_nivel: dict[str, set[int]] = {}
    for predicao in predicoes:
        por_nivel.setdefault(predicao["nivel_risco_predito"], set()).add(predicao["score_risco_predito"])
    assert any(len(valores) > 1 for valores in por_nivel.values()), "mesmo nível com scores distintos"

    for predicao in predicoes:
        minimo, maximo = _FAIXAS_NIVEL[predicao["nivel_risco_predito"]]
        assert minimo <= predicao["score_risco_predito"] <= maximo