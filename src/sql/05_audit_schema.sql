PRAGMA foreign_keys = ON;

-- Tabela de auditoria para rastrear chamadas à API, predições e acessos.
CREATE TABLE IF NOT EXISTS auditoria (
    id_auditoria INTEGER PRIMARY KEY AUTOINCREMENT,
    id_usuario INTEGER,
    acao TEXT NOT NULL,
    recurso TEXT,
    id_equipamento TEXT,
    id_registro INTEGER,
    detalhes TEXT,
    ip_origem TEXT,
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
    FOREIGN KEY (id_equipamento) REFERENCES equipamentos(id_equipamento),
    FOREIGN KEY (id_registro) REFERENCES telemetria(id_registro)
);

CREATE INDEX IF NOT EXISTS idx_auditoria_usuario ON auditoria(id_usuario);
CREATE INDEX IF NOT EXISTS idx_auditoria_acao ON auditoria(acao);
CREATE INDEX IF NOT EXISTS idx_auditoria_datahora ON auditoria(data_hora);
CREATE INDEX IF NOT EXISTS idx_auditoria_equipamento ON auditoria(id_equipamento);
