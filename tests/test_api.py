"""Testes de integração dos endpoints da API com TestClient (login, RBAC, telemetria)."""
from __future__ import annotations

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