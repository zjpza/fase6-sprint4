PRAGMA foreign_keys = ON;

-- Catálogo da frota monitorada pelo AgroRisk AI.
CREATE TABLE IF NOT EXISTS equipamentos (
    id_equipamento TEXT PRIMARY KEY,
    tipo_equipamento TEXT NOT NULL CHECK(tipo_equipamento IN ('Colheitadeira', 'Trator', 'Pulverizador')),
    estado_uf TEXT NOT NULL CHECK(estado_uf IN ('MT', 'GO', 'BA', 'RS', 'PR', 'SP')),
    latitude_base REAL,
    longitude_base REAL,
    ano_fabricacao INTEGER,
    capacidade_carga_kg REAL,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Leituras históricas de telemetria e features geradas pelo ETL.
CREATE TABLE IF NOT EXISTS telemetria (
    id_registro INTEGER PRIMARY KEY,
    id_equipamento TEXT NOT NULL,
    data_hora TIMESTAMP NOT NULL,
    latitude REAL,
    longitude REAL,
    tipo_operacao TEXT NOT NULL CHECK(tipo_operacao IN ('Campo', 'Transporte')),
    proximidade_agua_m INTEGER,
    precipitacao_mm REAL,
    umidade_solo_pct REAL,
    tipo_solo TEXT CHECK(tipo_solo IN ('Argiloso', 'Arenoso', 'Misto')),
    declividade_graus REAL,
    temperatura_c REAL,
    velocidade_vento_kmh REAL,
    visibilidade_m INTEGER,
    horas_uso_equipamento INTEGER,
    dias_ultima_manutencao INTEGER,
    velocidade_operacao_kmh REAL,
    carga_pct REAL,
    nivel_combustivel_pct REAL,
    historico_incidentes INTEGER,
    score_risco INTEGER CHECK(score_risco BETWEEN 0 AND 100),
    nivel_risco TEXT CHECK(nivel_risco IN ('Baixo', 'Médio', 'Alto', 'Crítico')),
    alerta_gerado INTEGER CHECK(alerta_gerado IN (0, 1)),
    tipo_solo_encoded INTEGER,
    tipo_operacao_encoded INTEGER,
    faixa_proximidade_agua TEXT,
    faixa_proximidade_encoded INTEGER,
    indice_desgaste REAL,
    risco_solo REAL,
    risco_atolamento REAL,
    risco_operacional REAL,
    risco_manutencao REAL,
    score_risco_calculado INTEGER,
    diff_score REAL,
    data_ingestao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_equipamento) REFERENCES equipamentos(id_equipamento)
);

-- Predições de modelos de ML para auditoria posterior.
CREATE TABLE IF NOT EXISTS scores_modelo (
    id_score INTEGER PRIMARY KEY AUTOINCREMENT,
    id_registro INTEGER NOT NULL,
    id_equipamento TEXT NOT NULL,
    data_hora_predicao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    score_risco_predito INTEGER CHECK(score_risco_predito BETWEEN 0 AND 100),
    nivel_risco_predito TEXT CHECK(nivel_risco_predito IN ('Baixo', 'Médio', 'Alto', 'Crítico')),
    alerta_predito INTEGER CHECK(alerta_predito IN (0, 1)),
    modelo_utilizado TEXT NOT NULL,
    probabilidades TEXT,
    fatores_principais TEXT,
    FOREIGN KEY (id_registro) REFERENCES telemetria(id_registro),
    FOREIGN KEY (id_equipamento) REFERENCES equipamentos(id_equipamento)
);

-- Histórico de alertas exibidos para operação e gestão.
CREATE TABLE IF NOT EXISTS alertas (
    id_alerta INTEGER PRIMARY KEY AUTOINCREMENT,
    id_registro INTEGER NOT NULL,
    id_equipamento TEXT NOT NULL,
    data_hora_alerta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    nivel_risco TEXT NOT NULL CHECK(nivel_risco IN ('Baixo', 'Médio', 'Alto', 'Crítico')),
    score_risco INTEGER NOT NULL CHECK(score_risco BETWEEN 0 AND 100),
    mensagem TEXT NOT NULL,
    tipo_alerta TEXT CHECK(tipo_alerta IN ('Preventivo', 'Crítico', 'Transporte')),
    lido INTEGER DEFAULT 0 CHECK(lido IN (0, 1)),
    FOREIGN KEY (id_registro) REFERENCES telemetria(id_registro),
    FOREIGN KEY (id_equipamento) REFERENCES equipamentos(id_equipamento)
);

-- Usuários e papéis para simular RBAC da solução.
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT UNIQUE,
    senha_hash TEXT,
    role TEXT NOT NULL CHECK(role IN ('Operador', 'GestorFrota', 'AnalistaSeguradora')),
    id_equipamento_acesso TEXT,
    ativo INTEGER DEFAULT 1 CHECK(ativo IN (0, 1)),
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_equipamento_acesso) REFERENCES equipamentos(id_equipamento)
);

CREATE INDEX IF NOT EXISTS idx_telemetria_equipamento ON telemetria(id_equipamento);
CREATE INDEX IF NOT EXISTS idx_telemetria_datahora ON telemetria(data_hora);
CREATE INDEX IF NOT EXISTS idx_telemetria_nivelrisco ON telemetria(nivel_risco);
CREATE INDEX IF NOT EXISTS idx_telemetria_alerta ON telemetria(alerta_gerado);
CREATE INDEX IF NOT EXISTS idx_scores_equipamento ON scores_modelo(id_equipamento);
CREATE INDEX IF NOT EXISTS idx_scores_datahora ON scores_modelo(data_hora_predicao);
CREATE INDEX IF NOT EXISTS idx_alertas_equipamento ON alertas(id_equipamento);

-- Garante consistência entre nível de risco e alerta gerado.
CREATE TRIGGER IF NOT EXISTS trg_valida_alerta
BEFORE INSERT ON telemetria
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN NEW.nivel_risco IN ('Alto', 'Crítico') AND NEW.alerta_gerado = 0 THEN
            RAISE(ABORT, 'Inconsistência: nivel_risco Alto/Crítico exige alerta_gerado=1')
        WHEN NEW.nivel_risco IN ('Baixo', 'Médio') AND NEW.alerta_gerado = 1 THEN
            RAISE(ABORT, 'Inconsistência: nivel_risco Baixo/Médio exige alerta_gerado=0')
    END;
END;
