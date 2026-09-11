PRAGMA foreign_keys = ON;

-- Equipamentos demonstrativos para abrir o banco mesmo antes da carga do ETL.
INSERT OR IGNORE INTO equipamentos
    (id_equipamento, tipo_equipamento, estado_uf, latitude_base, longitude_base, ano_fabricacao, capacidade_carga_kg)
VALUES
    ('EQ-MT-0023', 'Colheitadeira', 'MT', -13.4295, -56.7891, 2019, 15000),
    ('EQ-MT-0031', 'Trator', 'MT', -13.4310, -56.7910, 2021, 8000),
    ('EQ-GO-0012', 'Pulverizador', 'GO', -17.8821, -51.0932, 2020, 5000),
    ('EQ-SP-0008', 'Trator', 'SP', -22.9105, -47.0626, 2022, 9000),
    ('EQ-RS-0019', 'Trator', 'RS', -30.0346, -51.2177, 2018, 7500);

-- Usuários por persona para demonstrar RBAC.
INSERT OR IGNORE INTO usuarios (nome, email, senha_hash, role, id_equipamento_acesso) VALUES
    ('Carlos Silva', 'carlos@agrorisk.local', '$2b$12$9tKATY.UHIATYfbllvEP6eK9rHJT04yyumO8jbl0tZw8oFV/uD6Yq', 'Operador', 'EQ-MT-0023'),
    ('Fernanda Costa', 'fernanda@agrorisk.local', '$2b$12$.iUcFsUUfEVgmyfRexJXfeekGvdxgoScWSECbvwz4SmepY9aa4Us.', 'GestorFrota', NULL),
    ('Ricardo Mendes', 'ricardo@sompo.local', '$2b$12$UVnBHAXEYjxU4JaNcmVWFOBy/j7KRIwRsgOQIcw.4Z0xhFkSJlc7K', 'AnalistaSeguradora', NULL);

-- Regras de negócio usadas para explicar a composição do score de risco.
CREATE TABLE IF NOT EXISTS regras_risco (
    id_regra INTEGER PRIMARY KEY,
    variavel TEXT NOT NULL,
    faixa_min REAL,
    faixa_max REAL,
    score_adicional INTEGER,
    descricao TEXT
);

INSERT OR IGNORE INTO regras_risco
    (id_regra, variavel, faixa_min, faixa_max, score_adicional, descricao)
VALUES
    (1, 'proximidade_agua_m', 0, 50, 30, 'Risco crítico: muito próximo à água'),
    (2, 'proximidade_agua_m', 50, 200, 20, 'Risco alto: proximidade moderada à água'),
    (3, 'proximidade_agua_m', 200, 500, 10, 'Risco médio: distância de segurança reduzida'),
    (4, 'umidade_solo_pct', 70, 100, 20, 'Solo saturado: alto risco de atolamento'),
    (5, 'declividade_graus', 15, 90, 10, 'Terreno muito íngreme'),
    (6, 'velocidade_operacao_kmh', 10, 100, 10, 'Velocidade excessiva em campo');
