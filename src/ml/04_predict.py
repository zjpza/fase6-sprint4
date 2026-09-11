import sqlite3
import pickle
import pandas as pd
import json
from datetime import datetime

MODEL_PATH = 'src/ml/models/risk_model.pkl'
DB_PATH    = 'sompo.db'

def main():
    with open(MODEL_PATH, 'rb') as f:
        artefato = pickle.load(f)
    print(f"[OK] Modelo carregado: {artefato['model_name']}")

    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql('SELECT * FROM telemetria', conn)
    conn.close()

    features = artefato['features']
    modelo   = artefato['model']
    le       = artefato['label_encoder']

    feats_ok = [f for f in features if f in df.columns]
    X        = df[feats_ok].fillna(0)
    y_pred   = modelo.predict(X)
    labels   = le.inverse_transform(y_pred)

    proba_list = modelo.predict_proba(X) if hasattr(modelo, 'predict_proba') else None

    # Como o modelo e de classificacao, o score predito e o ponto medio da
    # faixa da classe prevista (Baixo 0-25, Medio 26-50, Alto 51-75, Critico 76-100).
    SCORE_POR_NIVEL = {'Baixo': 12, 'Médio': 38, 'Alto': 63, 'Crítico': 88}

    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    agora  = datetime.now().isoformat()

    # Idempotencia: limpa predicoes anteriores para nao duplicar ao reexecutar.
    cursor.execute("DELETE FROM scores_modelo")

    registros = []
    for i, row in df.iterrows():
        nivel      = labels[i]
        id_reg     = int(row.get('id_registro', i))
        id_equip   = str(row.get('id_equipamento', ''))
        score      = SCORE_POR_NIVEL.get(nivel, 50)
        alerta     = 1 if nivel in ('Alto', 'Crítico') else 0
        proba_json = json.dumps({c: round(float(p), 4)
                                 for c, p in zip(le.classes_, proba_list[i])}) if proba_list is not None else '{}'
        registros.append((id_reg, id_equip, agora, score, nivel,
                          alerta, artefato['model_name'], proba_json, ''))

    cursor.executemany("""
        INSERT INTO scores_modelo
            (id_registro, id_equipamento, data_hora_predicao, score_risco_predito,
             nivel_risco_predito, alerta_predito, modelo_utilizado, probabilidades, fatores_principais)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, registros)

    conn.commit()
    conn.close()

    print(f"[OK] {len(registros)} predicoes salvas!")
    print(pd.Series(labels).value_counts().to_string())

if __name__ == '__main__':
    main()