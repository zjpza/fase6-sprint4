"""Treino e avaliação do modelo final de risco (issue #4).

Roda sobre o dataset tratado pelo ETL refinado (`data/processed/features.csv`),
revisa o conjunto de features com números (importância + cross-validation),
treina o Random Forest final e reescreve `src/ml/relatorio_metricas.md`.

Executável de duas formas, a partir da raiz do projeto:
- ``python src/ml/train_model.py``
- ``python -m src.ml.train_model``
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.preprocessing import LabelEncoder

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.validacao_dados import RelatorioHigiene, higienizar  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = ROOT / "data" / "processed" / "features.csv"
MODEL_PATH = Path(__file__).resolve().parent / "models" / "risk_model.pkl"
RELATORIO_PATH = Path(__file__).resolve().parent / "relatorio_metricas.md"

TARGET = "nivel_risco"
ORDEM_CLASSES = ["Baixo", "Médio", "Alto", "Crítico"]

# Features da Sprint 2 — a revisão abaixo decide quais ficam.
# `score_risco` e `score_risco_calculado` ficam de fora: o target deriva deles (vazamento).
FEATURES_SPRINT_2 = [
    "proximidade_agua_m",
    "precipitacao_mm",
    "umidade_solo_pct",
    "declividade_graus",
    "horas_uso_equipamento",
    "dias_ultima_manutencao",
    "velocidade_operacao_kmh",
    "carga_pct",
    "historico_incidentes",
    "risco_manutencao",
    "indice_desgaste",
    "tipo_solo_encoded",
    "faixa_proximidade_encoded",
]

# Conjuntos candidatos avaliados por cross-validation para cortar redundância.
CONJUNTOS_CANDIDATOS = {
    "Sprint 2 (13 features)": FEATURES_SPRINT_2,
    "sem risco_manutencao": [f for f in FEATURES_SPRINT_2 if f != "risco_manutencao"],
    "sem indice_desgaste": [f for f in FEATURES_SPRINT_2 if f != "indice_desgaste"],
    "sem os dois derivados": [
        f for f in FEATURES_SPRINT_2 if f not in ("risco_manutencao", "indice_desgaste")
    ],
    "sem faixa_proximidade_encoded": [
        f for f in FEATURES_SPRINT_2 if f != "faixa_proximidade_encoded"
    ],
    "sem risco_manutencao e sem faixa": [
        f for f in FEATURES_SPRINT_2 if f not in ("risco_manutencao", "faixa_proximidade_encoded")
    ],
}

HIPERPARAMETROS = {
    "n_estimators": 200,
    "max_depth": None,
    "min_samples_split": 5,
    "random_state": 42,
    "n_jobs": -1,
}

SEED = 42


def carregar_dataset() -> tuple[pd.DataFrame, RelatorioHigiene]:
    """Lê o dataset tratado pelo ETL, aplica a mesma higienização e mantém o que o modelo consome."""
    if not FEATURES_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {FEATURES_PATH}. Rode o pipeline do ETL (issue #3) antes do treino."
        )
    df = pd.read_csv(FEATURES_PATH)
    faltando = [coluna for coluna in (*FEATURES_SPRINT_2, TARGET) if coluna not in df.columns]
    if faltando:
        raise ValueError(f"Dataset sem colunas esperadas: {', '.join(faltando)}")

    # Mesma porta de entrada da carga no banco: o modelo consome o que passou pela
    # higienização (faltantes, duplicidades, domínios e faixas), não o CSV cru.
    df, higiene = higienizar(df)
    return df.dropna(subset=[*FEATURES_SPRINT_2, TARGET]), higiene


def avaliar_conjuntos(df: pd.DataFrame) -> dict[str, tuple[float, float]]:
    """Acurácia média e desvio por conjunto de features (CV k=5 estratificada)."""
    le = LabelEncoder().fit(ORDEM_CLASSES)
    y = le.transform(df[TARGET])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)

    resultados: dict[str, tuple[float, float]] = {}
    for nome, features in CONJUNTOS_CANDIDATOS.items():
        scores = cross_val_score(
            RandomForestClassifier(**HIPERPARAMETROS), df[features], y, cv=cv, scoring="accuracy", n_jobs=-1
        )
        resultados[nome] = (float(scores.mean()), float(scores.std()))
    return resultados


def escolher_features(resultados: dict[str, tuple[float, float]]) -> tuple[str, list[str]]:
    """Melhor conjunto por CV; empate (diferença < 0.5 p.p.) fica com o mais enxuto."""
    melhor = max(resultados, key=lambda nome: resultados[nome][0])
    media_melhor = resultados[melhor][0]
    empatados = [
        nome
        for nome, (media, _) in resultados.items()
        if media_melhor - media < 0.005 and len(CONJUNTOS_CANDIDATOS[nome]) < len(CONJUNTOS_CANDIDATOS[melhor])
    ]
    if empatados:
        melhor = min(empatados, key=lambda nome: (len(CONJUNTOS_CANDIDATOS[nome]), -resultados[nome][0]))
    return melhor, list(CONJUNTOS_CANDIDATOS[melhor])


def treinar_e_avaliar(df: pd.DataFrame, features: list[str]) -> dict:
    """Treina o modelo final e devolve as métricas do conjunto de teste."""
    le = LabelEncoder().fit(ORDEM_CLASSES)
    X, y = df[features], le.transform(df[TARGET])
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )

    modelo = RandomForestClassifier(**HIPERPARAMETROS).fit(X_train, y_train)
    y_pred = modelo.predict(X_test)
    probabilidades = modelo.predict_proba(X_test)

    classes = list(le.classes_)
    return {
        "modelo": modelo,
        "label_encoder": le,
        "features": features,
        "classes": classes,
        "X_test": X_test,
        "y_test": y_test,
        "y_pred": y_pred,
        "acuracia": float(accuracy_score(y_test, y_pred)),
        "relatorio_classes": classification_report(
            y_test, y_pred, target_names=classes, output_dict=True, zero_division=0
        ),
        "matriz_confusao": confusion_matrix(y_test, y_pred).tolist(),
        "auc_ovr_macro": float(
            roc_auc_score(y_test, probabilidades, multi_class="ovr", average="macro")
        ),
        "importancia_arvores": dict(zip(features, [float(v) for v in modelo.feature_importances_])),
        "importancia_permutacao": dict(
            zip(
                features,
                [
                    float(v)
                    for v in permutation_importance(
                        modelo, X_test, y_test, n_repeats=10, random_state=SEED, n_jobs=-1
                    ).importances_mean
                ],
            )
        ),
        "acuracia_baseline": float(
            accuracy_score(y_test, _baseline_proximidade(X_test, le))
        ),
        "n_treino": int(len(X_train)),
        "n_teste": int(len(X_test)),
    }


def _baseline_proximidade(X: pd.DataFrame, le: LabelEncoder) -> np.ndarray:
    """Baseline do domínio: classifica só pela distância até a água."""
    faixas = X["proximidade_agua_m"].apply(
        lambda distancia: (
            "Crítico" if distancia < 50 else "Alto" if distancia < 200 else "Médio" if distancia < 500 else "Baixo"
        )
    )
    return le.transform(faixas)


def _tabela_metricas(resultado: dict) -> str:
    linhas = ["| Classe | Precision | Recall | F1 | Registros |", "|--------|-----------|--------|----|-----------|"]
    for classe in resultado["classes"]:
        m = resultado["relatorio_classes"][classe]
        linhas.append(
            f"| {classe} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1-score']:.3f} | {int(m['support'])} |"
        )
    macro = resultado["relatorio_classes"]["macro avg"]
    linhas.append(
        f"| **macro avg** | {macro['precision']:.3f} | {macro['recall']:.3f} | {macro['f1-score']:.3f} | {int(macro['support'])} |"
    )
    return "\n".join(linhas)


def _tabela_confusao(resultado: dict) -> str:
    classes = resultado["classes"]
    cabecalho = "| Real \\ Previsto | " + " | ".join(classes) + " |"
    separador = "|" + "---|" * (len(classes) + 1)
    linhas = [cabecalho, separador]
    for classe, linha in zip(classes, resultado["matriz_confusao"]):
        linhas.append("| " + classe + " | " + " | ".join(str(v) for v in linha) + " |")
    return "\n".join(linhas)


def _tabela_importancia(resultado: dict) -> str:
    linhas = ["| Variável | Importância (árvores) | Queda de acurácia ao permutar |", "|---|---|---|"]
    ordenado = sorted(resultado["importancia_arvores"].items(), key=lambda par: par[1], reverse=True)
    for coluna, valor in ordenado:
        permutacao = resultado["importancia_permutacao"][coluna]
        linhas.append(f"| {coluna} | {valor:.4f} | {permutacao:+.4f} |")
    return "\n".join(linhas)


def _tabela_conjuntos(resultados: dict[str, tuple[float, float]], escolhido: str) -> str:
    linhas = ["| Conjunto de features | Nº | Acurácia CV (k=5) |", "|---|---|---|"]
    for nome, (media, desvio) in sorted(resultados.items(), key=lambda par: par[1][0], reverse=True):
        marca = " ✅ escolhido" if nome == escolhido else ""
        linhas.append(f"| {nome}{marca} | {len(CONJUNTOS_CANDIDATOS[nome])} | {media:.4f} ± {desvio:.4f} |")
    return "\n".join(linhas)


def escrever_relatorio(resultado: dict, conjuntos: dict[str, tuple[float, float]], escolhido: str, n_linhas: int) -> None:
    """Reescreve o relatório de métricas com os números do modelo final."""
    media_cv, desvio_cv = conjuntos[escolhido]
    texto = f"""# Relatório de Métricas — Sprint 4 (issue #4)

Modelo final retreinado sobre o dataset tratado pelo ETL refinado da #3
(`data/processed/features.csv`, {n_linhas} registros) — {resultado['n_treino']} para treino e
{resultado['n_teste']} para teste, split estratificado 80/20 com `random_state=42`.

**Modelo escolhido:** Random Forest (`n_estimators=200`, `min_samples_split=5`) — mesma família da
Sprint 2, mantida para dar continuidade à comparação de métricas entre sprints.

## Resumo

| Métrica | Baseline (só distância até a água) | Modelo |
|---|---|---|
| Acurácia (teste) | {resultado['acuracia_baseline']:.4f} | **{resultado['acuracia']:.4f}** |
| AUC (OvR macro) | — | **{resultado['auc_ovr_macro']:.4f}** |
| F1 macro | — | **{resultado['relatorio_classes']['macro avg']['f1-score']:.4f}** |
| Acurácia CV (k=5) | — | {media_cv:.4f} ± {desvio_cv:.4f} |

## Métricas por classe

{_tabela_metricas(resultado)}

O **recall de `Crítico` e `Alto`** é a métrica que mais importa no problema: deixar passar um
equipamento que o modelo consideraria perigoso custa mais caro (sinistro) do que um alerta
preventivo a mais. `AUC` (OvR macro) entra como medida de separabilidade que não depende do corte
escolhido — útil porque as quatro classes são ordinais e a fronteira entre "Alto" e "Crítico" é
sensível ao limiar.

## Matriz de confusão (teste)

{_tabela_confusao(resultado)}

## Revisão das variáveis

Conjuntos avaliados por cross-validation antes de fixar as features do modelo final:

{_tabela_conjuntos(conjuntos, escolhido)}

**Escolhido:** {escolhido} ({len(resultado['features'])} features) — {', '.join(f'`{f}`' for f in resultado['features'])}.

Importância no modelo final (impureza das árvores e queda de acurácia ao permutar cada variável
no conjunto de teste):

{_tabela_importancia(resultado)}

## Decisões

- **`score_risco` e `score_risco_calculado` não entram como features**: o rótulo (`nivel_risco`)
  deriva deles — usá-los seria vazamento de target, inflando a acurácia sem valor preditivo real.
- **`fatores` e features derivadas**: `risco_manutencao` e `indice_desgaste` são combinações de
  variáveis que já estão no conjunto; a decisão de mantê-las ou cortá-las foi tomada pelos
  números acima (CV), não por intuição.
- **Fatores exibidos na API** não saem desta importância global: cada predição calcula a
  contribuição local das variáveis (ver `docs/ml-score-e-fatores.md`).
- **Limitação estrutural — o rótulo vem da própria regra**: `nivel_risco` deriva de
  `score_risco`, heurística determinística sobre as próprias variáveis de entrada. As
  métricas acima medem quão bem o modelo **recupera a regra** (substituto suavizado com score
  contínuo, fatores locais e sinal de ambiguidade) — não uma estimativa independente de
  risco real. Em produção com dados da Sompo, o alvo deve ser desfecho observado (sinistro,
  near-miss, manutenção corretiva); o pipeline (`train_model.py` sobre a saída do ETL) já
  aceita esse troco de rótulo sem mudança estrutural.
"""
    RELATORIO_PATH.write_text(texto, encoding="utf-8")


def main() -> None:
    df, higiene = carregar_dataset()
    descartados = ", ".join(
        f"{motivo}={quantidade}" for motivo, quantidade in higiene.descartados.items() if quantidade
    )
    print(
        f"[OK] Dataset tratado: {len(df)} registros de {higiene.total_entrada}"
        + (f" (descartados: {descartados})" if descartados else "")
    )

    conjuntos = avaliar_conjuntos(df)
    escolhido, features = escolher_features(conjuntos)
    print(f"[OK] Conjunto de features escolhido: {escolhido} ({len(features)})")

    resultado = treinar_e_avaliar(df, features)
    print(f"[OK] Acurácia no teste: {resultado['acuracia']:.4f} | AUC OvR macro: {resultado['auc_ovr_macro']:.4f}")

    artefato = {
        "model": resultado["modelo"],
        "label_encoder": resultado["label_encoder"],
        "features": features,
        "model_name": "Random Forest",
        "cv_accuracy_mean": conjuntos[escolhido][0],
        "test_accuracy": resultado["acuracia"],
        "auc_ovr_macro": resultado["auc_ovr_macro"],
        "treinado_em": "Sprint 4 (issue #4) — dataset tratado da #3",
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as arquivo:
        pickle.dump(artefato, arquivo)
    print(f"[OK] Modelo salvo em {MODEL_PATH}")

    escrever_relatorio(resultado, conjuntos, escolhido, len(df))
    print(f"[OK] Relatório atualizado em {RELATORIO_PATH}")
    print(json.dumps({"features": features, "acuracia_teste": resultado["acuracia"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
