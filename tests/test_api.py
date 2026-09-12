"""Testes de integração dos endpoints da API com TestClient (login, RBAC, telemetria, auditoria)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    alertas = resp.json()
    assert isinstance(alertas, list) and alertas
    # Campos que o dashboard lê para montar o histórico do analista (tipo_alerta faltava aqui).
    assert {"id_alerta", "id_equipamento", "nivel_risco", "score_risco", "mensagem", "tipo_alerta"} <= set(alertas[0])
    assert alertas[0]["tipo_alerta"] in ("Preventivo", "Crítico")


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


# --- Sprint 4 (#6 SEGURANÇA): token, injeção e trilha de auditoria ---

def _token_forjado(email: str, segredo: str, expira_em_minutos: int) -> str:
    import jwt

    from security.auth import ALGORITHM

    expira = datetime.now(timezone.utc) + timedelta(minutes=expira_em_minutos)
    return jwt.encode({"sub": email, "role": "GestorFrota", "exp": expira}, segredo, algorithm=ALGORITHM)


def test_token_expirado_e_recusado(client):
    """Token vencido não vale mais: a expiração é validada a cada requisição."""
    from security.auth import SECRET_KEY

    expirado = _token_forjado(GESTOR[0], SECRET_KEY, expira_em_minutos=-5)

    resp = client.get("/api/v1/equipamentos", headers=_auth(expirado))

    assert resp.status_code == 401
    assert "expirado" in resp.json()["detail"].lower()


def test_token_com_assinatura_de_outro_segredo_e_recusado(client):
    """Token assinado com segredo diferente (tentativa de forjar acesso) é recusado."""
    forjado = _token_forjado(GESTOR[0], "segredo-de-outro-ambiente-com-32-bytes", expira_em_minutos=60)

    resp = client.get("/api/v1/equipamentos", headers=_auth(forjado))

    assert resp.status_code == 401
    assert "inválido" in resp.json()["detail"].lower()


def test_segredo_nao_fica_embutido_no_codigo():
    """Sem JWT_SECRET_KEY, a API usa um segredo aleatório — nada de default versionado (B10)."""
    from security.auth import SECRET_KEY

    assert SECRET_KEY != "agrorisk-dev-secret-change-me-32b"
    assert len(SECRET_KEY) >= 32


def test_sem_env_a_api_gera_segredo_efemero(tmp_path):
    """Processo sem JWT_SECRET_KEY: segredo aleatório de 32+ bytes e aviso no log (B10)."""
    import subprocess
    import sys
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1]
    ambiente = {"PATH": str(Path(sys.executable).parent), "SYSTEMROOT": "C:/Windows"}
    codigo = "\n".join(
        [
            "import sys, warnings",
            "sys.path.insert(0, 'src')",
            "with warnings.catch_warnings(record=True) as avisos:",
            "    warnings.simplefilter('always')",
            "    import security.auth as auth",
            "    print(len(auth.SECRET_KEY), auth.SECRET_KEY != 'agrorisk-dev-secret-change-me-32b',",
            "          any('JWT_SECRET_KEY' in str(w.message) for w in avisos))",
        ]
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], cwd=raiz, env=ambiente, capture_output=True, text=True
    )

    assert resultado.returncode == 0, resultado.stderr
    tamanho, diferente_do_default, avisou = resultado.stdout.split()
    assert int(tamanho) >= 32
    assert diferente_do_default == "True"
    assert avisou == "True"


def test_identificador_com_sql_nao_afeta_o_banco(client, db):
    """Entrada maliciosa em campo identificador é recusada pela validação, sem tocar o schema."""
    token = _login(client, *GESTOR)
    payload = {**TELEMETRIA_PAYLOAD, "id_equipamento": "EQ-MT-0023'; DROP TABLE telemetria; --"}

    resp = _post_telemetria(client, token, payload)

    assert resp.status_code == 422
    assert (
        db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='telemetria'").fetchone()
        is not None
    )


def test_decisao_de_risco_fica_na_auditoria(client, db):
    """A trilha registra a decisão do sistema (scores, alerta e fatores), não só o acesso."""
    token = _login(client, *GESTOR)

    _post_telemetria(client, token, {**TELEMETRIA_PAYLOAD, "id_coleta": 9100})

    decisao = db.execute(
        "SELECT * FROM auditoria WHERE acao = 'decisao_risco' ORDER BY id_auditoria DESC LIMIT 1"
    ).fetchone()
    assert decisao is not None
    assert "score_regra=" in decisao["detalhes"]
    assert "score_modelo=" in decisao["detalhes"]
    assert "fatores=" in decisao["detalhes"]
    assert decisao["id_registro"] is not None


def test_auditoria_consultavel_para_gestor_e_analista(client):
    """A trilha é legível por quem audita: gestor e analista enxergam usuário, ação e horário."""
    token_gestor = _login(client, *GESTOR)
    _post_telemetria(client, token_gestor, {**TELEMETRIA_PAYLOAD, "id_coleta": 9200})

    resp = client.get("/api/v1/auditoria?limit=5", headers=_auth(token_gestor))

    assert resp.status_code == 200
    eventos = resp.json()
    assert eventos
    assert {"data_hora", "usuario", "acao", "detalhes", "ip_origem"} <= set(eventos[0])

    resp_analista = client.get(
        "/api/v1/auditoria?acao=decisao_risco", headers=_auth(_login(client, *ANALISTA))
    )
    assert resp_analista.status_code == 200
    assert all(evento["acao"] == "decisao_risco" for evento in resp_analista.json())


def test_operador_nao_acessa_a_trilha_de_auditoria(client):
    """Operador não consulta a trilha (RBAC) — ela expõe a operação dos outros."""
    token = _login(client, *OPERADOR)

    resp = client.get("/api/v1/auditoria", headers=_auth(token))

    assert resp.status_code == 403