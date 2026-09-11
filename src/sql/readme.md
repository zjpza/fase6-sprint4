# src/sql
Scripts de banco de dados relacional do projeto AgroRisk AI.

## Objetivo

Persistir dados de telemetria, scores de risco e histórico de alertas em um banco relacional, garantindo integridade, rastreabilidade e auditoria para o Analista da Seguradora (US-07).

## Scripts (a implementar na Sprint 2)

- `01_schema.sql`: DDL com CREATE TABLE, índices, constraints e chaves estrangeiras. Deve criar as tabelas:
  - `equipamentos` — cadastro de máquinas (id, tipo, localização base)
  - `telemetria` — registros de sensores (timestamp, coordenadas, variáveis ambientais/operacionais)
  - `scores_risco` — resultados do modelo (score, nível, alerta, recomendação)
  - `alertas` — histórico de alertas emitidos (para auditoria do analista)
- `02_seed_data.sql`: INSERTs de dados de exemplo para testes iniciais.
- `README_SQL.md`: dicionário de dados completo e instruções de execução.

## Banco Utilizado

- **SQLite** para desenvolvimento local e prototipação rápida.
- **MySQL** (ou PostgreSQL) recomendado para produção, com replicação e backup.

## Principais Constraints

- Integridade referencial entre `telemetria` → `equipamentos`
- Índice em `data_hora` para consultas temporais
- Índice em `id_equipamento` para filtros por máquina
- Índice composto em `latitude, longitude` para consultas geoespaciais
- Restrição `CHECK` para garantir valores válidos de `nivel_risco` (Baixo, Médio, Alto, Crítico)

## Exemplo de View (a criar)

```sql
CREATE VIEW vw_risco_por_equipamento AS
SELECT e.id_equipamento, e.tipo_equipamento,
       COUNT(*) AS total_registros,
       SUM(CASE WHEN s.nivel_risco = 'Crítico' THEN 1 ELSE 0 END) AS total_critico,
       AVG(s.score_risco) AS score_medio
FROM equipamentos e
JOIN telemetria t ON e.id_equipamento = t.id_equipamento
JOIN scores_risco s ON t.id_registro = s.id_registro
GROUP BY e.id_equipamento;
```
