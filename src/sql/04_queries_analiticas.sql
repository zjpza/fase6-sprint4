-- Matriz de confusão entre risco real e predito, quando o modelo de ML existir.
SELECT
    nivel_real AS real,
    nivel_risco_predito AS predito,
    COUNT(*) AS quantidade
FROM vw_historico_scores
WHERE nivel_risco_predito IS NOT NULL
GROUP BY nivel_real, nivel_risco_predito
ORDER BY real, predito;

-- Distribuição de risco por equipamento.
SELECT
    id_equipamento,
    nivel_risco,
    COUNT(*) AS total,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY id_equipamento), 2) AS percentual
FROM telemetria
GROUP BY id_equipamento, nivel_risco
ORDER BY id_equipamento, nivel_risco;

-- Top 50 registros de maior risco para o gestor.
SELECT
    t.id_equipamento,
    t.data_hora,
    t.score_risco,
    t.nivel_risco,
    t.proximidade_agua_m,
    t.umidade_solo_pct,
    t.declividade_graus,
    e.estado_uf
FROM telemetria t
JOIN equipamentos e ON t.id_equipamento = e.id_equipamento
WHERE t.nivel_risco IN ('Alto', 'Crítico')
ORDER BY t.score_risco DESC
LIMIT 50;

-- Evolução temporal do risco por equipamento.
SELECT
    date(data_hora) AS data,
    id_equipamento,
    ROUND(AVG(score_risco), 2) AS score_medio_diario,
    MAX(score_risco) AS score_max_diario,
    COUNT(CASE WHEN alerta_gerado = 1 THEN 1 END) AS alertas_dia
FROM telemetria
GROUP BY date(data_hora), id_equipamento
ORDER BY data DESC, id_equipamento;

-- Correlação prática entre proximidade de água e nível de risco.
SELECT
    CASE
        WHEN proximidade_agua_m < 50 THEN 'Crítico (<50m)'
        WHEN proximidade_agua_m < 200 THEN 'Alto (50-200m)'
        WHEN proximidade_agua_m < 500 THEN 'Médio (200-500m)'
        ELSE 'Baixo (>=500m)'
    END AS faixa_proximidade,
    COUNT(*) AS total,
    ROUND(AVG(score_risco), 2) AS score_medio,
    COUNT(CASE WHEN nivel_risco = 'Crítico' THEN 1 END) AS total_critico
FROM telemetria
GROUP BY faixa_proximidade
ORDER BY score_medio DESC;
