-- Resumo para o gestor acompanhar risco por equipamento.
CREATE VIEW IF NOT EXISTS vw_resumo_risco_equipamento AS
SELECT
    t.id_equipamento,
    e.tipo_equipamento,
    e.estado_uf,
    COUNT(*) AS total_registros,
    ROUND(AVG(t.score_risco), 2) AS score_medio,
    MAX(t.score_risco) AS score_maximo,
    COUNT(CASE WHEN t.nivel_risco = 'Crítico' THEN 1 END) AS total_critico,
    COUNT(CASE WHEN t.nivel_risco = 'Alto' THEN 1 END) AS total_alto,
    COUNT(CASE WHEN t.alerta_gerado = 1 THEN 1 END) AS total_alertas,
    MAX(t.data_hora) AS ultima_atualizacao
FROM telemetria t
JOIN equipamentos e ON t.id_equipamento = e.id_equipamento
GROUP BY t.id_equipamento, e.tipo_equipamento, e.estado_uf;

-- Alertas recentes para operadores.
CREATE VIEW IF NOT EXISTS vw_alertas_recentes AS
SELECT
    a.id_alerta,
    a.id_equipamento,
    a.data_hora_alerta,
    a.nivel_risco,
    a.score_risco,
    a.mensagem,
    a.lido,
    t.latitude,
    t.longitude
FROM alertas a
JOIN telemetria t ON a.id_registro = t.id_registro
WHERE date(a.data_hora_alerta) = date('now')
ORDER BY a.data_hora_alerta DESC;

-- Auditoria de predições do modelo contra o score real calculado.
CREATE VIEW IF NOT EXISTS vw_historico_scores AS
SELECT
    t.id_registro,
    t.id_equipamento,
    t.data_hora,
    t.score_risco AS score_real,
    t.nivel_risco AS nivel_real,
    s.score_risco_predito,
    s.nivel_risco_predito,
    s.modelo_utilizado,
    ABS(t.score_risco - s.score_risco_predito) AS erro_absoluto,
    CASE WHEN t.nivel_risco = s.nivel_risco_predito THEN 1 ELSE 0 END AS acerto
FROM telemetria t
LEFT JOIN scores_modelo s ON t.id_registro = s.id_registro;

-- Exploração estatística entre solo, umidade, declividade e risco.
CREATE VIEW IF NOT EXISTS vw_correlacao_solo_risco AS
SELECT
    tipo_solo,
    COUNT(*) AS total_registros,
    ROUND(AVG(umidade_solo_pct), 2) AS umidade_media,
    ROUND(AVG(score_risco), 2) AS score_medio,
    ROUND(AVG(declividade_graus), 2) AS declividade_media,
    ROUND(AVG(proximidade_agua_m), 2) AS proximidade_agua_media,
    COUNT(CASE WHEN nivel_risco = 'Crítico' THEN 1 END) AS total_critico,
    ROUND(COUNT(CASE WHEN nivel_risco = 'Crítico' THEN 1 END) * 100.0 / COUNT(*), 2) AS pct_critico
FROM telemetria
GROUP BY tipo_solo;
