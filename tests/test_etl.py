"""Testes do ETL: idempotência da carga, higienização de dados sujos e rastreabilidade (issue #3).

O bootstrap de `sys.path` vem do `conftest.py`, carregado antes deste módulo.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from data import load_to_sql

SQL_DIR = Path(__file__).resolve().parents[1] / "src" / "sql"

# Colunas de features.csv = telemetria bruta + derivadas do feature engineering.
COLUNAS_FEATURES = [
    "id_registro",
    "id_equipamento",
    "tipo_equipamento",
    "data_hora",
    "latitude",
    "longitude",
    "tipo_operacao",
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
    "score_risco",
    "nivel_risco",
    "alerta_gerado",
    "tipo_solo_encoded",
    "tipo_operacao_encoded",
    "faixa_proximidade_agua",
    "faixa_proximidade_encoded",
    "indice_desgaste",
    "risco_solo",
    "risco_atolamento",
    "risco_operacional",
    "risco_manutencao",
    "score_risco_calculado",
    "diff_score",
]


def linha(id_registro: int, **overrides) -> dict:
    """Uma linha de features.csv válida e internamente consistente, com campos sobrescritíveis."""
    base = {
        "id_registro": id_registro,
        "id_equipamento": "EQ-MT-0023",
        "tipo_equipamento": "Colheitadeira",
        "data_hora": (datetime(2024, 3, 1, 8, 0, 0) + timedelta(seconds=id_registro)).strftime("%Y-%m-%d %H:%M:%S"),
        "latitude": -13.4295,
        "longitude": -56.7891,
        "tipo_operacao": "Campo",
        "proximidade_agua_m": 120,
        "precipitacao_mm": 42.5,
        "umidade_solo_pct": 68.0,
        "tipo_solo": "Argiloso",
        "declividade_graus": 8.0,
        "temperatura_c": 28.5,
        "velocidade_vento_kmh": 18.0,
        "visibilidade_m": 2800,
        "horas_uso_equipamento": 4200,
        "dias_ultima_manutencao": 35,
        "velocidade_operacao_kmh": 9.5,
        "carga_pct": 82.0,
        "nivel_combustivel_pct": 64.0,
        "historico_incidentes": 1,
        "score_risco": 88,
        "nivel_risco": "Alto",
        "alerta_gerado": True,
        "tipo_solo_encoded": 0,
        "tipo_operacao_encoded": 0,
        "faixa_proximidade_agua": "moderada",
        "faixa_proximidade_encoded": 2,
        "indice_desgaste": 0.42,
        "risco_solo": 0.55,
        "risco_atolamento": 0.61,
        "risco_operacional": 0.38,
        "risco_manutencao": 0.30,
        "score_risco_calculado": 86,
        "diff_score": 2.0,
    }
    base.update(overrides)
    return base


@dataclass
class AmbienteETL:
    """Banco e features.csv isolados por teste, com os caminhos que o ETL consulta."""

    db_path: Path
    features_path: Path

    def salvar_features(self, linhas: list[dict]) -> None:
        pd.DataFrame(linhas)[COLUNAS_FEATURES].to_csv(self.features_path, index=False)

    def registros(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in conn.execute("SELECT * FROM telemetria ORDER BY id_registro")]
        finally:
            conn.close()

    def contar(self, tabela: str) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])
        finally:
            conn.close()


@pytest.fixture
def etl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AmbienteETL:
    """Cria um banco novo (schema + seeds) e redireciona o ETL para ele."""
    db_path = tmp_path / "etl.db"
    features_path = tmp_path / "features.csv"

    conn = sqlite3.connect(db_path)
    for script in ("01_schema.sql", "02_seed_data.sql", "05_audit_schema.sql"):
        conn.executescript((SQL_DIR / script).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()

    monkeypatch.setattr(load_to_sql, "DB_PATH", db_path)
    monkeypatch.setattr(load_to_sql, "FEATURES_PATH", features_path)
    return AmbienteETL(db_path=db_path, features_path=features_path)


def test_recarga_da_mesma_fonte_nao_duplica_nem_insere_zero(etl: AmbienteETL):
    """Reexecutar o ETL sobre a mesma fonte não duplica registros nem finge sucesso com 0 inseridos."""
    etl.salvar_features([linha(1), linha(2, data_hora="2024-03-01 09:00:00")])

    primeira = load_to_sql.carregar_dados()
    segunda = load_to_sql.carregar_dados()

    assert (primeira.inseridos, primeira.coletas_ja_presentes) == (2, 0)
    assert (segunda.inseridos, segunda.coletas_ja_presentes) == (0, 2)
    assert len(etl.registros()) == 2


def test_cada_registro_guarda_a_origem(etl: AmbienteETL):
    """Cada linha carregada aponta para a coleta que a originou: fonte, id de coleta, equipamento e timestamp."""
    etl.salvar_features([linha(7, id_equipamento="EQ-GO-0012", data_hora="2024-04-02 14:30:00")])

    load_to_sql.carregar_dados()

    registro = etl.registros()[0]
    assert registro["fonte"] == "dataset_simulado"
    assert registro["id_coleta"] == 7
    assert registro["id_equipamento"] == "EQ-GO-0012"
    assert registro["data_hora"] == "2024-04-02 14:30:00"
    assert registro["data_ingestao"] is not None


def test_dataset_sujo_e_descartado_antes_de_entrar_no_banco(etl: AmbienteETL):
    """Linhas faltantes, duplicadas, fora de range ou incoerentes são descartadas com motivo — e o banco fica íntegro."""
    etl.salvar_features(
        [
            linha(1),
            linha(2, data_hora="2024-03-01 08:00:01"),  # duplicata da chave natural (equipamento + data_hora)
            linha(3, umidade_solo_pct=float("nan")),  # faltante em coluna obrigatória
            linha(4, tipo_operacao="Voador"),  # fora do domínio declarado no schema
            linha(5, score_risco=150, score_risco_calculado=150),  # fora do range 0-100
            linha(6, nivel_risco="Baixo", alerta_gerado=False, score_risco=10),  # coerente
            linha(7, nivel_risco="Baixo", alerta_gerado=True, score_risco=10),  # incoerente (trigger rejeitaria)
        ]
    )

    resultado = load_to_sql.carregar_dados()

    assert resultado.inseridos == 2
    assert resultado.higiene.descartados == {
        "duplicado": 1,
        "faltante": 1,
        "dominio_invalido": 1,
        "fora_de_range": 1,
        "inconsistente": 1,
    }
    assert [registro["id_coleta"] for registro in etl.registros()] == [1, 6]


def test_linha_sem_id_de_coleta_nao_entra(etl: AmbienteETL):
    """Sem id de coleta não há rastreabilidade: a linha é descartada com motivo, não quebra a carga."""
    sem_origem = linha(2, data_hora="2024-03-01 09:00:00")
    sem_origem["id_registro"] = float("nan")
    etl.salvar_features([linha(1), sem_origem, linha(3)])

    resultado = load_to_sql.carregar_dados()

    assert resultado.inseridos == 2
    assert resultado.higiene.descartados["faltante"] == 1
    assert [registro["id_coleta"] for registro in etl.registros()] == [1, 3]


def test_fonte_sem_coluna_de_rastreabilidade_falha_com_mensagem_clara(etl: AmbienteETL):
    """Fonte sem a coluna de origem é contrato quebrado — erro nomeado, não KeyError no meio da carga."""
    etl.salvar_features([linha(1)])
    sem_origem = pd.read_csv(etl.features_path).drop(columns=["id_registro"])
    sem_origem.to_csv(etl.features_path, index=False)

    with pytest.raises(ValueError, match="id_registro"):
        load_to_sql.carregar_dados()


@pytest.mark.parametrize(
    ("coluna", "valor_invalido"),
    [("tipo_operacao", "Voador"), ("tipo_solo", "Vulcânico"), ("nivel_risco", "Extremo")],
)
def test_dominio_recusado_na_higiene_e_o_mesmo_recusado_pelo_schema(
    etl: AmbienteETL, coluna: str, valor_invalido: str
):
    """As duas camadas concordam: o valor que a higienização descarta é o que o CHECK do schema recusa."""
    from data.validacao_dados import higienizar

    _, relatorio = higienizar(pd.DataFrame([linha(1, **{coluna: valor_invalido})]))
    assert relatorio.descartados["dominio_invalido"] == 1

    campos = {
        "id_equipamento": "EQ-MT-0023",
        "data_hora": "2024-05-01 10:00:00",
        "tipo_operacao": "Campo",
        "tipo_solo": "Misto",
        "nivel_risco": "Alto",
        "alerta_gerado": 1,
        coluna: valor_invalido,
    }
    conn = sqlite3.connect(etl.db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO telemetria ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
                tuple(campos.values()),
            )
    finally:
        conn.close()


def test_carga_sem_registro_integro_falha_alto(etl: AmbienteETL):
    """Se a fonte não tem nenhuma linha aproveitável, a carga falha em vez de concluir com 0 registros."""
    etl.salvar_features([linha(1, umidade_solo_pct=float("nan"))])

    with pytest.raises(ValueError, match="íntegra|integr"):
        load_to_sql.carregar_dados()


def test_linha_que_fere_o_schema_estoura_em_vez_de_sumir(etl: AmbienteETL):
    """Recusa do banco (UF inexistente no CHECK) precisa aparecer como erro, não virar carga silenciosa de 0."""
    etl.salvar_features([linha(1, id_equipamento="EQ-XX-0001")])

    with pytest.raises(sqlite3.IntegrityError, match="estado_uf"):
        load_to_sql.carregar_dados()


def _schema_sem_rastreabilidade() -> str:
    """DDL do projeto como era antes da Sprint 4: sem as colunas fonte/id_coleta."""
    ddl = (SQL_DIR / "01_schema.sql").read_text(encoding="utf-8")
    linhas = [
        linha
        for linha in ddl.splitlines()
        if "id_coleta" not in linha and "fonte" not in linha
    ]
    # A cláusula UNIQUE saiu junto: a FK de telemetria não pode ficar com vírgula pendurada.
    return "\n".join(linhas).replace(
        "REFERENCES equipamentos(id_equipamento),", "REFERENCES equipamentos(id_equipamento)"
    )


def test_base_legada_recebe_rastreabilidade_e_volta_a_carregar(etl: AmbienteETL, monkeypatch: pytest.MonkeyPatch):
    """Banco anterior à Sprint 4 (sem fonte/id_coleta) é migrado pelo schema e volta a aceitar carga."""
    from data import pipeline

    etl.db_path.unlink()
    conn = sqlite3.connect(etl.db_path)
    conn.executescript(_schema_sem_rastreabilidade())
    conn.executescript((SQL_DIR / "02_seed_data.sql").read_text(encoding="utf-8"))
    conn.commit()
    conn.close()

    monkeypatch.setattr(pipeline, "DB_PATH", etl.db_path)
    pipeline.executar_schema()

    etl.salvar_features([linha(1)])
    resultado = load_to_sql.carregar_dados()

    assert resultado.inseridos == 1
    assert etl.registros()[0]["id_coleta"] == 1


def test_mesma_medicao_com_coleta_nova_nao_entra_duas_vezes(etl: AmbienteETL):
    """Reimportar a mesma medição com id de coleta diferente é ignorado: o banco não acumula duplicatas."""
    etl.salvar_features([linha(1)])
    load_to_sql.carregar_dados()

    etl.salvar_features([linha(99, data_hora=linha(1)["data_hora"])])  # mesma máquina/instante, outro id de coleta
    resultado = load_to_sql.carregar_dados()

    assert (resultado.inseridos, resultado.medicoes_ja_registradas) == (0, 1)
    assert len(etl.registros()) == 1


@pytest.mark.parametrize(
    "sujeira",
    [
        {"umidade_solo_pct": float("nan")},
        {"carga_pct": -10},
        {"tipo_solo": "Vulcânico"},
        {"nivel_risco": "Baixo", "alerta_gerado": True, "score_risco": 10},
    ],
    ids=["faltante", "fora_de_range", "dominio_invalido", "inconsistente"],
)
def test_sujeira_da_fonte_nao_derruba_a_carga_inteira(etl: AmbienteETL, sujeira: dict):
    """Uma linha ruim no meio do lote não impede as boas de entrar nem deixa a base pela metade."""
    etl.salvar_features([linha(1), linha(2, **sujeira), linha(3)])

    resultado = load_to_sql.carregar_dados()

    assert resultado.inseridos == 2
    assert resultado.higiene.total_descartados == 1
    assert [registro["id_coleta"] for registro in etl.registros()] == [1, 3]
