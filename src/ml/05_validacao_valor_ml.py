"""Experimentos que medem o valor do modelo sobre a regra (deduções 1 e 2 da avaliação).

A regra determinística (`score_regra`) gerou o rótulo do dataset; o modelo foi
treinado nesse rótulo. Este script quantifica, com números reproduzíveis
(seed 42), o que o modelo agrega de fato em quatro eixos:

  [1] divergência regra×modelo por distância da fronteira de banda
      — o modelo detecta ambiguidade onde a soma determinística é instável?
  [2] robustez a ruído ±10% nas entradas
      — quem troca de nível menos sob perturbação: regra ou modelo?
  [3] granularidade do score contínuo dentro da banda
      — o modelo ordena dentro da banda onde a regra empata?
  [4] sensibilidade dos 11 pesos da regra
      — qual peso é decisivo e qual é irrelevante para calibrar com a Sompo?

Base: ``data/processed/features.csv`` (mesmo CSV do treino e do ``04_predict.py``).

Executar a partir da raiz do projeto:

``python src/ml/05_validacao_valor_ml.py``
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ml.features import calcular_features, classificar_risco, componentes_regra, score_regra  # noqa: E402
from ml.predictor import RiskPredictor  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = ROOT / "data" / "processed" / "features.csv"

# Fronteiras entre as bandas de FAIXAS_NIVEL (0-25, 26-50, 51-75, 76-100):
# um score inteiro cai na banda de cima a partir de 26, 51 e 76.
FRONTEIRAS = (25.5, 50.5, 75.5)

# Features numéricas perturbáveis no experimento de ruído (categóricas intactas).
FEATURES_PERTURBAVEIS = [
    "proximidade_agua_m",
    "precipitacao_mm",
    "umidade_solo_pct",
    "declividade_graus",
    "horas_uso_equipamento",
    "dias_ultima_manutencao",
    "velocidade_operacao_kmh",
    "carga_pct",
    "visibilidade_m",
    "historico_incidentes",
]
FEATURES_0_100 = {"umidade_solo_pct", "carga_pct"}


def main() -> None:
    if not FEATURES_PATH.exists():
        raise SystemExit("Features ausentes — rode python src/data/pipeline.py antes")

    df = pd.read_csv(FEATURES_PATH)
    for coluna in ("tipo_operacao", "tipo_solo"):
        if coluna not in df.columns:
            raise SystemExit(f"Coluna ausente no CSV: {coluna} — rode python src/data/pipeline.py antes")

    np.random.seed(42)
    n = len(df)

    # --- Base: regra e modelo sobre os mesmos registros ---
    regra = df.apply(lambda r: score_regra(calcular_features(r.to_dict())), axis=1)
    nivel_regra = regra.map(classificar_risco)

    pred = RiskPredictor().predict(df)
    nivel_modelo = pred["nivel_risco_predito"]
    score_modelo = pred["score_risco_predito"]

    # --- [1] Divergência por distância da fronteira de banda ---
    dist = pd.concat([np.abs(regra - f) for f in FRONTEIRAS], axis=1).min(axis=1)
    perto = dist <= 5
    longe = ~perto
    div = nivel_regra != nivel_modelo

    print(f"[1] divergência por distância da fronteira")
    print(f"    base: {n} registros")
    print(
        f"    dist <= 5 da fronteira: {int(perto.sum())} registros, "
        f"divergência regra x modelo: {div[perto].mean() * 100:.1f}%"
    )
    print(
        f"    dist  > 5 da fronteira: {int(longe.sum())} registros, "
        f"divergência regra x modelo: {div[longe].mean() * 100:.1f}%"
    )

    # --- [2] Robustez a ruído ±10% nas entradas ---
    df_ruido = df.copy()
    for coluna in FEATURES_PERTURBAVEIS:
        ruido = df_ruido[coluna] * np.random.uniform(0.9, 1.1, size=n)
        if coluna in FEATURES_0_100:
            df_ruido[coluna] = ruido.clip(0, 100)
        else:
            df_ruido[coluna] = ruido.clip(lower=0)

    nivel_regra_ruido = df_ruido.apply(
        lambda r: classificar_risco(score_regra(calcular_features(r.to_dict()))), axis=1
    )
    nivel_modelo_ruido = RiskPredictor().predict(df_ruido)["nivel_risco_predito"]

    troca_regra = (nivel_regra_ruido != nivel_regra).mean() * 100
    troca_modelo = (nivel_modelo_ruido != nivel_modelo).mean() * 100
    print(f"[2] robustez a ruído ±10%")
    print(f"    base: {n} registros, ruído multiplicativo uniforme(0.9, 1.1) por célula")
    print(f"    regra  — troca de nível: {troca_regra:.1f}% dos registros")
    print(f"    modelo — troca de nível: {troca_modelo:.1f}% dos registros")

    # --- [3] Granularidade dentro da banda ---
    print(f"[3] granularidade dentro da banda")
    for banda in ("Alto", "Crítico"):
        na_banda = nivel_regra == banda
        valores_regra = regra[na_banda].nunique()
        valores_modelo = score_modelo[na_banda].round().astype(int).nunique()
        print(
            f"    banda {banda}: {int(na_banda.sum())} registros | "
            f"valores distintos da regra: {valores_regra} | "
            f"valores distintos do score do modelo: {valores_modelo}"
        )

    # --- [4] Sensibilidade dos 11 pesos da regra ---
    comps = [componentes_regra(calcular_features(r.to_dict())) for _, r in df.iterrows()]
    nomes = list(comps[0].keys())
    niveis_base = nivel_regra.tolist()

    linhas = []
    for nome in nomes:
        mudancas = {}
        for fator in (0.8, 1.2):
            troca = 0
            for comp, nivel_base in zip(comps, niveis_base):
                score_alt = int(
                    min(100, max(0, sum(v * (fator if k == nome else 1.0) for k, v in comp.items())))
                )
                if classificar_risco(score_alt) != nivel_base:
                    troca += 1
            mudancas[fator] = troca / n * 100
        linhas.append((nome, mudancas[0.8], mudancas[1.2]))

    linhas.sort(key=lambda l: max(l[1], l[2]), reverse=True)
    print(f"[4] sensibilidade dos pesos da regra")
    print(f"    base: {n} registros | % que muda de nível ao multiplicar o peso por 0.8 / 1.2")
    print(f"    {'componente':<28}{'-20%':>10}{'+20%':>10}")
    for nome, menos, mais in linhas:
        print(f"    {nome:<28}{menos:>9.1f}%{mais:>9.1f}%")


if __name__ == "__main__":
    main()