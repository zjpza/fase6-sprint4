"""Carga de features.csv na tabela `telemetria` com rastreabilidade até a fonte.

Recarregar a mesma fonte é idempotente: cada linha é identificada por
``(fonte, id_coleta)`` e uma coleta já presente é ignorada, não duplicada
nem "inserida 0" em silêncio (achado B2 da auditoria).
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Bootstrap para que `data.*` resolva nos dois modos de execução, sem depender de cwd.
SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.conexao import conectar  # noqa: E402
from data.validacao_dados import RelatorioHigiene, higienizar  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = ROOT / "data" / "processed" / "features.csv"
DB_PATH = ROOT / "sompo.db"
TABLE_NAME = "telemetria"

#: Identifica no banco de onde a coleta veio (a carga do ETL, não a API).
FONTE_ETL = "dataset_simulado"

#: Capacidade nominal por tipo de equipamento, usada ao cadastrar frota descoberta no dataset.
CAPACIDADE_POR_TIPO = {"Colheitadeira": 15000, "Trator": 8000, "Pulverizador": 5000}


@dataclass(frozen=True)
class ResultadoCarga:
    """Resultado da carga: o que entrou, o que já existia e o que foi descartado por qualidade."""

    inseridos: int
    coletas_ja_presentes: int
    medicoes_ja_registradas: int
    higiene: RelatorioHigiene

    @property
    def total(self) -> int:
        """Total de registros da fonte considerados nesta carga."""
        return self.inseridos + self.coletas_ja_presentes + self.medicoes_ja_registradas

    def resumo(self) -> str:
        """Texto único do resultado, usado por quem imprime a carga."""
        descartados = ", ".join(
            f"{motivo}={quantidade}"
            for motivo, quantidade in self.higiene.descartados.items()
            if quantidade
        )
        texto = (
            f"{self.inseridos} inseridos, {self.coletas_ja_presentes} coletas já presentes, "
            f"{self.medicoes_ja_registradas} medições já registradas"
        )
        return texto + (f", descartados por qualidade ({descartados})" if descartados else "")


def _marcar_por_coleta(dados: pd.DataFrame, ja_presentes: set[tuple[str, int]]) -> list[bool]:
    """Marca as linhas cuja coleta (fonte + id) já está no banco."""
    if not ja_presentes:
        return [False] * len(dados)
    return [
        (str(fonte), int(coleta)) in ja_presentes
        for fonte, coleta in zip(dados["fonte"], dados["id_coleta"])
    ]


def contar_registros() -> int:
    """Quantidade de registros hoje na tabela de telemetria."""
    with conectar(DB_PATH) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0])


def carregar_equipamentos(conn: sqlite3.Connection, df: pd.DataFrame) -> None:
    """Cadastra a frota descoberta no dataset.

    A frota demonstrativa é responsabilidade de `02_seed_data.sql` — aqui só
    entram equipamentos que aparecem na fonte, para não manter a mesma lista
    de seeds em dois lugares.
    """
    if not conn.execute("PRAGMA table_info(equipamentos)").fetchall():
        return

    dataset_equipamentos = (
        df.groupby("id_equipamento")
        .agg(
            tipo_equipamento=("tipo_equipamento", "first"),
            latitude_base=("latitude", "mean"),
            longitude_base=("longitude", "mean"),
        )
        .reset_index()
    )
    dataset_equipamentos["estado_uf"] = dataset_equipamentos["id_equipamento"].str.split("-").str[1]
    dataset_equipamentos["ano_fabricacao"] = 2020
    dataset_equipamentos["capacidade_carga_kg"] = dataset_equipamentos["tipo_equipamento"].map(
        CAPACIDADE_POR_TIPO
    )

    colunas_equipamento = [
        "id_equipamento",
        "tipo_equipamento",
        "estado_uf",
        "latitude_base",
        "longitude_base",
        "ano_fabricacao",
        "capacidade_carga_kg",
    ]
    ja_cadastrados = {
        row[0] for row in conn.execute("SELECT id_equipamento FROM equipamentos")
    }
    novos = dataset_equipamentos[
        ~dataset_equipamentos["id_equipamento"].isin(ja_cadastrados)
    ][colunas_equipamento]

    # INSERT puro: equipamento fora do padrão do schema (ex.: UF inexistente)
    # precisa estourar na hora, não ser ignorado junto com a telemetria.
    conn.executemany(
        f"INSERT INTO equipamentos ({', '.join(colunas_equipamento)}) VALUES (?, ?, ?, ?, ?, ?, ?)",
        novos.itertuples(index=False, name=None),
    )


def obter_colunas_tabela(conn: sqlite3.Connection) -> list[str]:
    """Colunas existentes na tabela de destino; falha se o schema não foi aplicado."""
    colunas = conn.execute(f"PRAGMA table_info({TABLE_NAME})").fetchall()
    if not colunas:
        raise RuntimeError(f"Tabela '{TABLE_NAME}' não existe em {DB_PATH}. Crie o schema SQL antes da carga.")
    return [coluna[1] for coluna in colunas]


def preparar_dataframe(df: pd.DataFrame, colunas_tabela: list[str]) -> pd.DataFrame:
    """Monta as colunas do insert traduzindo o id da planilha em rastreabilidade.

    `id_registro` é a PK do banco (o banco atribui) e `data_ingestao` é
    timestamp de ingestão: nenhum dos dois vem da fonte. O id da planilha vira
    `id_coleta`, acompanhado de `fonte`, para que recarregar não colida com PKs.
    """
    df = df.copy()
    if "alerta_gerado" in df.columns:
        df["alerta_gerado"] = df["alerta_gerado"].astype(int)  # bool já normalizado na higienização

    df["fonte"] = FONTE_ETL
    df["id_coleta"] = df["id_registro"]

    colunas_geradas_pelo_banco = {"id_registro", "data_ingestao"}
    colunas_insert = [
        coluna
        for coluna in colunas_tabela
        if coluna in df.columns and coluna not in colunas_geradas_pelo_banco
    ]
    return df[colunas_insert]


def coletas_ja_presentes(conn: sqlite3.Connection) -> set[tuple[str, int]]:
    """Pares (fonte, id_coleta) que já estão no banco, para não recarregar a mesma coleta."""
    return {
        (str(fonte), int(id_coleta))
        for fonte, id_coleta in conn.execute(
            f"SELECT fonte, id_coleta FROM {TABLE_NAME} WHERE fonte = ? AND id_coleta IS NOT NULL",
            (FONTE_ETL,),
        )
    }


def instantes_ja_registrados(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """Pares (equipamento, instante) já no banco — a mesma medição vinda com outro id de coleta."""
    return {
        (str(id_equipamento), str(data_hora))
        for id_equipamento, data_hora in conn.execute(
            f"SELECT id_equipamento, data_hora FROM {TABLE_NAME}"
        )
    }


def carregar_dados() -> ResultadoCarga:
    """Carrega features.csv no banco e devolve o resultado da carga."""
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {FEATURES_PATH}. Rode feature_engineering.py primeiro."
        )

    df = pd.read_csv(FEATURES_PATH)
    dados, higiene = higienizar(df)
    if higiene.total_aproveitado == 0:
        motivos = ", ".join(f"{motivo}={quantidade}" for motivo, quantidade in higiene.descartados.items())
        raise ValueError(
            f"Nenhuma linha íntegra em {FEATURES_PATH} ({higiene.total_entrada} linhas descartadas: {motivos})."
        )

    with conectar(DB_PATH) as conn:
        carregar_equipamentos(conn, dados)
        colunas_tabela = obter_colunas_tabela(conn)
        dados = preparar_dataframe(dados, colunas_tabela)
        if dados.empty:
            raise ValueError(f"Nada a carregar de {FEATURES_PATH} em {TABLE_NAME}.")

        com_rastreabilidade = "id_coleta" in dados.columns
        ja_carregadas = pd.Series(
            _marcar_por_coleta(dados, coletas_ja_presentes(conn)) if com_rastreabilidade else False,
            index=dados.index,
        )
        instantes = instantes_ja_registrados(conn)
        mesma_medicao = pd.Series(
            [
                (str(id_equipamento), str(data_hora)) in instantes
                for id_equipamento, data_hora in zip(dados["id_equipamento"], dados["data_hora"])
            ],
            index=dados.index,
        ) & ~ja_carregadas
        novas = dados[~(ja_carregadas | mesma_medicao)]

        if not novas.empty:
            placeholders = ", ".join(["?"] * len(novas.columns))
            colunas_sql = ", ".join(novas.columns)
            # INSERT puro de propósito: linha que fere CHECK/FK/gatilho deve estourar,
            # não ser engolida em silêncio como acontecia com o INSERT OR IGNORE (B2).
            conn.executemany(
                f"INSERT INTO {TABLE_NAME} ({colunas_sql}) VALUES ({placeholders})",
                novas.itertuples(index=False, name=None),
            )
            conn.commit()

    return ResultadoCarga(
        inseridos=len(novas),
        coletas_ja_presentes=int(ja_carregadas.sum()),
        medicoes_ja_registradas=int(mesma_medicao.sum()),
        higiene=higiene,
    )


def main() -> None:
    resultado = carregar_dados()
    print(f"Carga em {DB_PATH}:{TABLE_NAME} — {resultado.resumo()}")


if __name__ == "__main__":
    main()
