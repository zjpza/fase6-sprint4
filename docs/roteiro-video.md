# Roteiro do vídeo — Sprint 4 (≤ 5 min, YouTube não listado)

Objetivo do enunciado: **mostrar na tela** o fluxo funcionando de ponta a ponta (não só narrar).
A lacuna apontada no feedback da Sprint 3 foi exatamente essa: o vídeo anterior mostrou só a visão
do operador e descreveu o resto em voz.

## Preparação (antes de gravar)

```bash
# 1. ambiente limpo e banco reconstruído (garante números redondos na gravação)
pip install -r requirements.txt
python -c "import secrets; print(secrets.token_urlsafe(32))"   # cole em .env como JWT_SECRET_KEY
python src/data/pipeline.py
# → [OK] Carga: 997 inseridos ... [OK] Pipeline concluído com sucesso (997 registros em telemetria).

# 2. dois terminais: API e dashboard (dashboard entra direto com a persona)
python -m uvicorn start_api:app --host 127.0.0.1 --port 8000
DASHBOARD_DEMO_LOGIN=gestor python -m streamlit run src/dashboard/app.py
#    (no Windows: set DASHBOARD_DEMO_LOGIN=gestor  → depois o comando do streamlit)

# 3. abas abertas: dashboard (http://127.0.0.1:8501) e docs da API (http://127.0.0.1:8000/docs)
```

## Cenas

| # | Tempo | O que aparece na tela | Fala (resumo) |
|---|---|---|---|
| 1 | 0:00-0:25 | README aberto no diagrama de arquitetura | "AgroRisk AI, FIAP + Sompo. Pipeline: coleta simulada → ETL higienizado e rastreável → API FastAPI → SQLite → modelo → dashboard, com auditoria das decisões." |
| 2 | 0:25-0:50 | Terminal: `python src/data/pipeline.py` rodando | "O ETL carrega 997 registros e **descarta 3 duplicidades com motivo**. Rodando de novo, ele insere 0 e informa '997 já presentes' — a carga é idempotente e cada registro guarda fonte e id de coleta." |
| 3 | 0:50-1:35 | Terminal: `python src/api/simulador_telemetria.py --n 5 --interval 1 --lote 1` | "O simulador autentica, envia telemetria e imprime a resposta: score da regra, score do modelo, o alerta (decisão da regra) e a marca de divergência. Cada envio tem id de coleta: reenviar o mesmo dá 409, sem duplicar." |
| 4 | 1:35-2:00 | Swagger (`/docs`): `POST /api/v1/telemetria` expandido e a resposta JSON | "Na API a entrada é validada por Pydantic; o serviço calcula as features, o score da regra, chama o modelo e grava telemetria, score, alerta e a decisão na trilha — tudo na mesma transação." |
| 5 | 2:00-2:40 | Dashboard como **Operador** (Carlos) | "Visão do operador: score da regra 58 e score do modelo 33 — mesma escala, então dá para ver quando discordam. O alerta cita as penalidades da regra com os pontos de cada uma e a segunda opinião do modelo; a regra decide, o modelo sinaliza ambiguidade." |
| 6 | 2:40-3:30 | Dashboard como **Gestor** (Fernanda) | "Visão da gestora: mapa de risco da frota, distribuição por nível, evolução, tendência por região e score por tipo de operação, além do critério de classificação explícito na tela." |
| 7 | 3:30-4:10 | Dashboard como **Analista** (Ricardo) + exportação CSV | "Visão da analista: histórico de alertas com exportação e a trilha de auditoria — quem acessou, quando, e o que o sistema decidiu, com scores, alerta e fatores de cada registro." |
| 8 | 4:10-4:40 | Terminal: `python -m pytest tests/ -q` | "80 testes passando, incluindo um fluxo completo ETL → API → score → alerta da regra → auditoria." |
| 9 | 4:40-5:00 | Volta ao README (decisões técnicas e prints) | "As decisões de cada correção estão registradas em docs/, com as evidências das issues #1 a #9." |

## Checklist antes de publicar

- [ ] Duração ≤ 5 min
- [ ] **Fluxo mostrado na tela** (não só narrado): coleta → resposta da API com score/fatores → alerta → as 3 visões
- [ ] Narração humana (sem TTS)
- [ ] Publicar no YouTube como **não listado**
- [ ] Colar o link no README (`## 🎥 Apresentação em Vídeo`) e na issue #9
- [ ] Confirmar que a tela não expõe segredo real (`.env` não aparece; use `JWT_SECRET_KEY` local)

## Dicas de gravação

- Resolução 1080p, fontes do terminal aumentadas (Ctrl + +) e dashboard em 100% de zoom.
- Enviar poucos registros por vez (`--n 5`) para a saída caber na tela.
- Se algo der errado ao vivo, mostre o erro e a mensagem clara — as falhas tratadas (API fora do ar, payload inválido) também são resultado do trabalho.
- `--lote 1` cria coletas novas; sem ele, reenvios aparecem como "já registrados" (útil se quiser demonstrar idempotência ao vivo).
