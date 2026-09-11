from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "src" / "ml" / "models" / "risk_model.pkl"

# Pontos médios das faixas de risco (score 0-100)
SCORE_POR_NIVEL = {"Baixo": 12, "Médio": 38, "Alto": 63, "Crítico": 88}


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

    def _extrair_top_features(self, row: pd.Series) -> list[str]:
        """Retorna as 3 features com maior contribuição absoluta para o score calculado."""
        features_numericas = [
            "umidade_solo_pct",
            "proximidade_agua_m",
            "precipitacao_mm",
            "declividade_graus",
            "velocidade_operacao_kmh",
            "carga_pct",
            "horas_uso_equipamento",
            "dias_ultima_manutencao",
            "historico_incidentes",
            "velocidade_vento_kmh",
            "temperatura_c",
        ]
        valores = {col: abs(float(row.get(col, 0))) for col in features_numericas if col in row}
        return [col for col, _ in sorted(valores.items(), key=lambda x: x[1], reverse=True)[:3]]

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
        for i, row in df.iterrows():
            nivel = labels[i]
            score = SCORE_POR_NIVEL.get(nivel, 50)
            alerta = nivel in ("Alto", "Crítico")
            proba_json = (
                json.dumps(
                    {
                        c: round(float(p), 4)
                        for c, p in zip(self._label_encoder.classes_, proba_list[i])
                    }
                )
                if proba_list is not None
                else "{}"
            )
            fatores = self._extrair_top_features(row)
            resultados.append(
                {
                    "id_registro": int(row.get("id_registro", i)),
                    "id_equipamento": str(row.get("id_equipamento", "")),
                    "score_risco_predito": score,
                    "nivel_risco_predito": nivel,
                    "alerta_predito": int(alerta),
                    "modelo_utilizado": self.model_name,
                    "probabilidades": proba_json,
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
