"""Testes de integração dos endpoints da API com TestClient (login, RBAC, telemetria)."""
from __future__ import annotations

import pytest

TELEMETRIA_PAYLOAD = {
    "id_equipamento": "EQ-MT-0023",
    "tipo_operacao": "Campo",
    "latitude": -13.4295,
    "longitude": -56.7891,
    "proximidade_agua_m": 30,
    "precipitacao_mm": 50,
    "umidade_solo_pct": 90,
    "tipo_solo": "Argiloso",
    "declividade_graus": 15,
    "temperatura_c": 28,
    "velocidade_vento_kmh": 12,
    "visibilidade_m": 200,
    "horas_uso_equipamento": 5000,
    "dias_ultima_manutencao": 60,
    "velocidade_operacao_kmh": 10,
    "carga_pct": 95,
    "nivel_combustivel_pct": 40,
    "historico_incidentes": 3,
}

OPERADOR = ("carlos@agrorisk.local", "operador123")
GESTOR = ("fernanda@agrorisk.local", "gestor123")
ANALISTA = ("ricardo@sompo.local", "analista123")


def _login(client, email: str, senha: str) -> str:
    resp = client.post("/api/v1/login", json={"email": email, "senha": senha})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _post_telemetria(client, token: str, payload: dict):
    return client.post("/api/v1/telemetria", json=payload, headers=_auth(token))


def test_login_correto(client):
    resp = client.post("/api/v1/login", json={"email": OPERADOR[0], "senha": OPERADOR[1]})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_login_senha_errada(client):
    resp = client.post("/api/v1/login", json={"email": OPERADOR[0], "senha": "wrong"})
    assert resp.status_code == 401


def test_telemetria_sem_token(client):
    resp = client.post("/api/v1/telemetria", json=TELEMETRIA_PAYLOAD)
    assert resp.status_code == 401


def test_telemetria_operador_ok(client):
    token = _login(client, *OPERADOR)
    resp = _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "score_risco" in body
    assert "nivel_risco" in body
    assert "nivel_risco_predito" in body


def test_telemetria_operador_equipo_errado(client):
    token = _login(client, *OPERADOR)
    payload = {**TELEMETRIA_PAYLOAD, "id_equipamento": "EQ-MT-0031"}
    resp = _post_telemetria(client, token, payload)
    assert resp.status_code == 403


def test_telemetria_analista_proibido(client):
    token = _login(client, *ANALISTA)
    resp = _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
    assert resp.status_code == 403


def test_get_telemetria_operador_filtrado(client):
    token = _login(client, *OPERADOR)
    for _ in range(3):
        resp = _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
        assert resp.status_code == 201
    resp = client.get("/api/v1/telemetria", headers=_auth(token))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) >= 1
    assert all(r["id_equipamento"] == "EQ-MT-0023" for r in rows)


def test_get_telemetria_gestor_tudo(client):
    token = _login(client, *GESTOR)
    for _ in range(5):
        resp = _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
        assert resp.status_code == 201
    resp = client.get("/api/v1/telemetria?limit=5", headers=_auth(token))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 5
    assert all("tipo_equipamento" in r for r in rows)
    assert all("nivel_risco_predito" in r for r in rows)


def test_get_equipamentos(client):
    token = _login(client, *GESTOR)
    resp = client.get("/api/v1/equipamentos", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) >= 5


def test_get_alertas(client):
    token = _login(client, *GESTOR)
    _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
    resp = client.get("/api/v1/alertas", headers=_auth(token))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_me(client):
    token = _login(client, *OPERADOR)
    resp = client.get("/api/v1/me", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == OPERADOR[0]
    assert body["role"] == "Operador"
    assert body["id_equipamento_acesso"] == "EQ-MT-0023"
    assert "id_usuario" in body and "nome" in body


def test_me_sem_token(client):
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401


def test_telemetria_erro_interno(client):
    """Erro no predictor → 500 com mensagem genérica, sem vazar internals."""
    token = _login(client, *GESTOR)

    class _BadPredictor:
        def predict(self, df):
            raise RuntimeError("boom-sensitive-info-123")

    client.app.state.predictor = _BadPredictor()
    resp = _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Erro interno ao processar telemetria"
    assert "boom-sensitive-info-123" not in resp.text


def test_audit_view(client, db):
    """vw_historico_scores computa erro_absoluto/acerto honestamente após um POST."""
    token = _login(client, *GESTOR)
    resp = _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
    id_registro = resp.json()["id_registro"]
    row = db.execute(
        "SELECT erro_absoluto, acerto FROM vw_historico_scores WHERE id_registro = ?",
        (id_registro,),
    ).fetchone()
    assert row is not None
    assert row["acerto"] in (0, 1)
    assert row["erro_absoluto"] >= 0


def test_resumo_frota(client):
    token = _login(client, *GESTOR)
    for _ in range(3):
        _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
    resp = client.get("/api/v1/resumo-frota", headers=_auth(token))
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    assert any(r["id_equipamento"] == "EQ-MT-0023" for r in rows)
    assert all("score_medio" in r for r in rows)


# --- Sprint 4 (#2 REFACT): exceções e validações nos pontos de contato ---

def test_telemetria_equipamento_inexistente(client):
    """Payload válido + equipamento não cadastrado -> 422 claro, não 500 de FK."""
    token = _login(client, *GESTOR)
    payload = {**TELEMETRIA_PAYLOAD, "id_equipamento": "EQ-XX-9999"}
    resp = _post_telemetria(client, token, payload)
    assert resp.status_code == 422
    assert "não cadastrado" in resp.json()["detail"]


def test_telemetria_rejeitada_fica_na_auditoria(client, db):
    """Entrada rejeitada deve deixar rastro auditável (regra + motivo), não sumir.

    O id do equipamento vai em `detalhes` porque auditoria.id_equipamento tem
    FK para equipamentos — um id não cadastrado violaria a chave.
    """
    token = _login(client, *GESTOR)
    payload = {**TELEMETRIA_PAYLOAD, "id_equipamento": "EQ-XX-9999"}
    _post_telemetria(client, token, payload)
    row = db.execute(
        "SELECT acao, detalhes FROM auditoria WHERE acao = ? ORDER BY id_auditoria DESC LIMIT 1",
        ("telemetria_rejeitada",),
    ).fetchone()
    assert row is not None
    assert "EQ-XX-9999" in row["detalhes"]


def test_telemetria_limit_fora_do_padrao(client):
    """limit inválido (0, negativo, >1000) deve ser 422, não consulta sem limites."""
    token = _login(client, *GESTOR)
    for bad in ("0", "-1", "1001", "abc"):
        resp = client.get(f"/api/v1/telemetria?limit={bad}", headers=_auth(token))
        assert resp.status_code == 422, f"limit={bad} deveria ser 422, veio {resp.status_code}"


def test_telemetria_limit_valido_mantem_paginacao(client):
    token = _login(client, *GESTOR)
    for _ in range(3):
        _post_telemetria(client, token, TELEMETRIA_PAYLOAD)
    resp = client.get("/api/v1/telemetria?limit=2", headers=_auth(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_telemetria_limit_no_teto_do_dashboard(client):
    """O dashboard pede o histórico no teto do parâmetro: esse limite precisa continuar aceito."""
    token = _login(client, *GESTOR)
    _post_telemetria(client, token, TELEMETRIA_PAYLOAD)

    resp = client.get("/api/v1/telemetria?limit=1000", headers=_auth(token))

    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- Sprint 4 (#5 INTEGRAÇÃO): confiabilidade da coleta ---

def test_coleta_reenviada_nao_duplica_dado(client, db):
    """Reenviar a mesma coleta (mesmo id_coleta) devolve 409 e não grava segunda vez."""
    token = _login(client, *GESTOR)
    payload = {**TELEMETRIA_PAYLOAD, "id_coleta": 4242}

    primeira = _post_telemetria(client, token, payload)
    segunda = _post_telemetria(client, token, payload)

    assert primeira.status_code == 201
    assert segunda.status_code == 409
    assert str(primeira.json()["id_registro"]) in segunda.json()["detail"]

    registros = db.execute(
        "SELECT COUNT(*) FROM telemetria WHERE fonte = 'api' AND id_coleta = 4242"
    ).fetchone()[0]
    scores = db.execute(
        "SELECT COUNT(*) FROM scores_modelo WHERE id_registro = ?", (primeira.json()["id_registro"],)
    ).fetchone()[0]
    assert (registros, scores) == (1, 1)


def test_coleta_sem_id_explicito_continua_aceitando_envios(client, db):
    """Sem id de coleta declarado, cada envio é uma medição (comportamento anterior preservado)."""
    token = _login(client, *GESTOR)

    for _ in range(2):
        assert _post_telemetria(client, token, TELEMETRIA_PAYLOAD).status_code == 201

    assert db.execute("SELECT COUNT(*) FROM telemetria WHERE id_coleta IS NULL").fetchone()[0] == 2


def test_rajada_de_envios_persiste_tudo_com_score(client, db):
    """Rajada (sem intervalo) não perde nem duplica: enviados = persistidos = com score."""
    token = _login(client, *GESTOR)
    total = 15

    respostas = [
        _post_telemetria(client, token, {**TELEMETRIA_PAYLOAD, "id_coleta": 7000 + i})
        for i in range(total)
    ]

    assert [r.status_code for r in respostas] == [201] * total
    persistidos = db.execute(
        "SELECT COUNT(*) FROM telemetria WHERE id_coleta BETWEEN 7000 AND 8000"
    ).fetchone()[0]
    com_score = db.execute(
        """
        SELECT COUNT(*) FROM telemetria t
        JOIN scores_modelo sm ON sm.id_registro = t.id_registro
        WHERE t.id_coleta BETWEEN 7000 AND 8000
        """
    ).fetchone()[0]
    assert (persistidos, com_score) == (total, total)


@pytest.mark.parametrize(
    "alteracao",
    [
        {"umidade_solo_pct": 150},          # fora da faixa
        {"tipo_solo": "Vulcânico"},         # fora do domínio
        {"latitude": 200},                  # coordenada impossível
        {"historico_incidentes": -1},       # contagem negativa
    ],
    ids=["faixa", "dominio", "coordenada", "contagem"],
)
def test_payload_malformado_e_recusado_sem_gravar(client, db, alteracao: dict):
    """Payload fora das regras devolve 422 e não deixa meia gravação no banco."""
    token = _login(client, *GESTOR)
    payload = {**TELEMETRIA_PAYLOAD, **alteracao, "id_coleta": 8001}

    resp = _post_telemetria(client, token, payload)

    assert resp.status_code == 422
    assert db.execute("SELECT COUNT(*) FROM telemetria WHERE id_coleta = 8001").fetchone()[0] == 0


def test_payload_sem_campo_obrigatorio_e_recusado(client, db):
    """Campo obrigatório ausente é 422 — o registro não entra pela metade."""
    token = _login(client, *GESTOR)
    payload = {chave: valor for chave, valor in TELEMETRIA_PAYLOAD.items() if chave != "umidade_solo_pct"}

    resp = _post_telemetria(client, token, payload)

    assert resp.status_code == 422
    assert db.execute("SELECT COUNT(*) FROM telemetria").fetchone()[0] == 0