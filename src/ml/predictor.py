"""Inferência de risco: score contínuo e fatores por contribuição real (issue #4).

O score deixa de ser um valor fixo por classe (Sprint 3) e passa a vir das
probabilidades do modelo, na mesma escala 0-100 da regra. Os fatores principais
saem de perturbação local: quanto a probabilidade do nível predito muda quando
aquela variável é perturbada naquele registro — sensibilidade local, não valor
absoluto bruto da variável.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

from ml.features import score_continuo

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "src" / "ml" / "models" / "risk_model.pkl"

# Mudança mínima na probabilidade (em pontos percentuais) para a variável contar como fator.
LIMITE_CONTRIBUICAO = 0.01

# Variáveis discretas: o passo de perturbação é uma unidade (limitada ao domínio).
FEATURES_DISCRETAS = {
    "historico_incidentes": (0, None),
    "tipo_solo_encoded": (0, 2),
    "faixa_proximidade_encoded": (0, 3),
}


class RiskPredictor:
    """Wrapper para carregar e usar o modelo Random Forest treinado na Sprint 2."""

    def __init__(self, model_path: Path | str | None = None) -> None:
        self.model_path = Path(model_path) if model_path else MODEL_PATH
        self._artefato: dict | None = None
        self._model = None
        self._label_encoder = None
        self._features: list[str] = []
        self._carregar()

    def _carregar(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"Modelo não encontrado: {self.model_path}")
        with self.model_path.open("rb") as file:
            self._artefato = pickle.load(file)
        self._model = self._artefato["model"]
        self._label_encoder = self._artefato["label_encoder"]
        self._features = self._artefato["features"]

    @property
    def model_name(self) -> str:
        return str(self._artefato.get("model_name", "desconhecido"))

    def _valores_perturbados(self, coluna: str, valor: float) -> list[float]:
        """Valores alternativos de uma variável para medir seu efeito local.

        Contínuas variam ±20%; discretas (contagens e categorias codificadas)
        variam uma unidade dentro do domínio — passos que o operador reconhece.
        """
        if coluna in FEATURES_DISCRETAS:
            minimo, maximo = FEATURES_DISCRETAS[coluna]
            candidatos = [valor - 1, valor + 1]
            return [
                candidato
                for candidato in candidatos
                if candidato >= minimo and (maximo is None or candidato <= maximo)
            ]
        return [valor * 0.8, valor * 1.2]

    def _fatores_por_contribuicao(self, row: pd.Series, base: dict[str, float], nivel: str) -> list[str]:
        """Top-3 variáveis que mais movem a probabilidade do nível predito neste registro.

        Sensibilidade local (uma variável por vez, dentro do próprio registro):
        a variável entra como fator porque mexer nela muda a predição, e não
        porque o valor dela é numericamente grande.
        """
        variantes: list[pd.Series] = []
        origens: list[str] = []
        for coluna in self._features:
            if coluna not in row.index:
                continue
            for candidato in self._valores_perturbados(coluna, float(row[coluna])):
                variante = row.copy()
                variante[coluna] = candidato
                variantes.append(variante)
                origens.append(coluna)

        if not variantes or nivel not in base:
            return []

        classes = list(self._label_encoder.classes_)
        probabilidades = self._model.predict_proba(pd.DataFrame(variantes)[self._features])
        prob_base = base[nivel]
        indice_nivel = classes.index(nivel)

        contribuicoes: dict[str, float] = {}
        for coluna, linha in zip(origens, probabilidades):
            efeito = abs(float(linha[indice_nivel]) - prob_base)
            contribuicoes[coluna] = max(contribuicoes.get(coluna, 0.0), efeito)

        relevantes = [par for par in contribuicoes.items() if par[1] >= LIMITE_CONTRIBUICAO]
        return [coluna for coluna, _ in sorted(relevantes, key=lambda par: par[1], reverse=True)[:3]]

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """Recebe um DataFrame de telemetria e retorna predições por registro."""
        if df.empty:
            return pd.DataFrame()

        df = df.copy()
        feats_ok = [f for f in self._features if f in df.columns]
        if not feats_ok:
            raise ValueError(f"Nenhuma feature esperada encontrada. Esperadas: {self._features}")

        X = df[feats_ok].fillna(0)
        y_pred = self._model.predict(X)
        labels = self._label_encoder.inverse_transform(y_pred)

        proba_list = (
            self._model.predict_proba(X)
            if hasattr(self._model, "predict_proba")
            else None
        )

        resultados = []
        for posicao, (_, row) in enumerate(df.iterrows()):
            nivel = labels[posicao]
            probabilidades = (
                {
                    str(c): round(float(p), 4)
                    for c, p in zip(self._label_encoder.classes_, proba_list[posicao])
                }
                if proba_list is not None
                else {}
            )
            score = round(score_continuo(probabilidades)) if probabilidades else 50
            alerta = nivel in ("Alto", "Crítico")
            fatores = self._fatores_por_contribuicao(row, probabilidades, str(nivel))
            resultados.append(
                {
                    "id_registro": int(row.get("id_registro", posicao)),
                    "id_equipamento": str(row.get("id_equipamento", "")),
                    "score_risco_predito": int(min(100, max(0, score))),
                    "nivel_risco_predito": nivel,
                    "alerta_predito": int(alerta),
                    "modelo_utilizado": self.model_name,
                    "probabilidades": json.dumps(probabilidades),
                    "fatores_principais": json.dumps(fatores),
                }
            )
        return pd.DataFrame(resultados)

    def recomendacao(self, nivel: str, fatores: list[str]) -> str:
        """Gera uma recomendação textual simples baseada no nível e nos fatores principais."""
        if nivel == "Crítico":
            base = "🚨 Risco crítico detectado. Suspender a operação imediatamente e acionar o gestor de frota."
        elif nivel == "Alto":
            base = "⚠️ Risco alto. Reduzir velocidade, evitar áreas alagadiças e monitorar condições do solo."
        elif nivel == "Médio":
            base = "⚡ Atenção moderada. Acompanhar evolução do clima e do terreno."
        else:
            base = "✅ Operação dentro de parâmetros seguros."

        if fatores:
            base += f" Fatores principais: {', '.join(fatores)}."
        return base


def predict_from_records(records: list[dict]) -> list[dict]:
    """Função utilitária para predizer a partir de uma lista de dicionários."""
    df = pd.DataFrame(records)
    predictor = RiskPredictor()
    result = predictor.predict(df)
    return result.to_dict(orient="records")
