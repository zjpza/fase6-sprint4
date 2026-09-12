# Relatórios e prints do dashboard — Sprint 4 (issue #7)

O que cada perfil vê, com que critério o sistema alerta e as capturas das três visões
(a lacuna apontada no feedback da Sprint 3 era a ausência de prints no repositório).

## Prints das visões finais (`assets/prints/`)

| Print | Perfil | O que mostra |
|---|---|---|
| [`01-gestor-frota.png`](../assets/prints/01-gestor-frota.png) | Fernanda (Gestor de Frota) | KPIs da frota, mapa de risco por região, distribuição por nível, evolução do risco médio, **tendência por região**, **score médio por tipo de operação**, critérios de risco e tabela com risco (regra) × risco (ML) |
| [`02-operador-campo.png`](../assets/prints/02-operador-campo.png) | Carlos (Operador) | Status do equipamento, **score da regra × score do modelo (com delta)**, **fatores que pesaram na predição**, alerta que cita as causas reais, condições atuais e histórico de score |
| [`03-analista-seguradora.png`](../assets/prints/03-analista-seguradora.png) | Ricardo (Analista) | Histórico auditável de alertas + **trilha de auditoria** (quem acessou, o que o sistema decidiu) com exportação CSV |

Como as capturas foram feitas: dashboard rodando de verdade contra a API, com
`DASHBOARD_DEMO_LOGIN=<perfil>` (entra com o usuário de demonstração e permite capturar a tela
sem digitar). Sem essa variável, o dashboard usa o formulário normal de login.

## Critério de alerta (explícito e legível)

O mesmo critério aparece na tela (`Critério de classificação`) e vale para regra e modelo:

| Faixa de score (0-100) | Nível |
|---|---|
| 0-25 | Baixo |
| 26-50 | Médio |
| 51-75 | Alto |
| 76-100 | Crítico |

- **Alerta preventivo** é emitido quando o nível é **Alto** ou **Crítico** — o operador vê
  `Risco (regra)` e `Risco (ML)` lado a lado justamente para perceber quando discordam.
- O texto do alerta cita os **fatores que pesaram no registro**, não uma causa fixa (antes dizia
  sempre "proximidade de água e umidade do solo", mesmo quando nenhuma das duas pesava).
- `score_risco` (regra) e `score_risco_predito` (modelo) compartilham a escala 0-100 — detalhes
  em [`ml-score-e-fatores.md`](ml-score-e-fatores.md).

## Aderência por persona (User Stories)

| Persona | User Story | O que a visão entrega |
|---|---|---|
| Operador (Carlos) | US-01 — alerta antes de entrar em área de risco | Status do próprio equipamento, alerta com causas, recomendação direta e histórico recente |
| Gestor de Frota (Fernanda) | US-04 — mapa com status por equipamento | Mapa de risco, KPIs da frota, distribuição por nível, evolução, tendência por região e por tipo de operação |
| Analista da Seguradora (Ricardo) | US-07 — histórico de alertas antes de um sinistro | Histórico exportável de alertas + trilha de auditoria das decisões, com exportação CSV |

## O que mudou nesta issue

1. **Tendências por dimensão**: além da evolução geral, o gestor vê score médio por **região** ao
   longo do tempo e por **tipo de operação** no estado atual.
2. **Critérios legíveis na tela**: bloco com as faixas e a regra de alerta, reaproveitando
   `ml.features.FAIXAS_NIVEL` (fonte única do domínio) em vez de repetir números na interface.
3. **Trilha de auditoria no perfil do analista**: consome `GET /api/v1/auditoria` (issue #6) com
   filtro por ação, contadores e exportação CSV.
4. **Mapa sem dependência externa**: o mapa passou de `scatter_map` (tiles de rua + WebGL) para
   `scatter_geo` (mapa embutido no Plotly). Motivo prático: com tiles externos o mapa ficava em
   branco em print e em navegador sem WebGL — o print do repositório saía sem mapa.
5. **Bugs encontrados ao validar as telas** (ambos quebravam a visão do analista):
   - `GET /api/v1/alertas` não devolvia `tipo_alerta` (o `response_model` filtrava a coluna) → a
     tabela do analista estourava com `KeyError`; campo adicionado ao schema e coberto por teste.
   - O sidebar renderizava **dois campos de Email** (um fora do formulário, sem placeholder),
     resquício de edição anterior; removido.

## Limitações declaradas

- As visões usam a leitura mais recente por equipamento para o estado atual e até 1000 registros
  para as séries (teto do `limit` da API) — suficiente para a frota de demonstração.
- O export CSV sai do próprio Streamlit (`st.download_button`), sem endpoint dedicado.
- Gráficos são Plotly interativos; os prints são estáticos (o vídeo cobre a interação).
