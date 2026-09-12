# Confiabilidade da coleta — Sprint 4 (issue #5)

Validação de que a telemetria flui da coleta até o banco/modelo sem perda, sem duplicação e sem
corrupção — e do que o simulador faz quando a rede ou a API falham.

## O que foi validado

| Cenário | Antes | Agora |
|---|---|---|
| Reenvio da mesma coleta | gravava duas vezes a mesma medição | **409** com o registro existente, sem duplicar |
| Rajada (sem intervalo) | não havia medição de consistência | enviados = persistidos = com score, comprovado |
| Equipamento do operador | simulador enviava frota aleatória → 403 em cascata | `--equipamento` coleta para o equipamento informado |
| Falha transitória (5xx, timeout) | registro perdido com `ERRO HTTP` | **3 tentativas** com backoff exponencial |
| Token expirado (401) | re-login e uma retentativa | mantido, agora dentro do mesmo fluxo de retry |
| API fora do ar | traceback cru do httpx | mensagem clara (`API inacessível em … — ConnectError`) e saída com código 1 |
| Payload fora do padrão | 422 (desde a #2) | 422 mantido, verificado que **nada** é gravado |

## O que mudou

1. **Identidade da coleta na API** (`POST /telemetria`): campo opcional `id_coleta`. Com ele, a
   mesma coleta (`fonte='api'` + `id_coleta`) não entra duas vezes — a API responde **409** com o
   `id_registro` existente e registra `telemetria_duplicada` na auditoria. Sem o campo, o
   comportamento anterior é preservado (cada envio é uma medição).
2. **Retry e resumo no simulador**: 3 tentativas com backoff para 5xx/timeout, re-login em 401 e
   um resumo final (`enviados | aceitos | já registrados | rejeitados | falhas`) com código de
   saída 1 quando há rejeição ou falha — o script deixa de "terminar bem" sem ter entregado tudo.
3. **`--equipamento`**: envia os registros como se viessem do equipamento informado. É o que
   permite a coleta do operador (que só pode postar do próprio equipamento) sem depender de o
   dataset sortear aquele id.
4. **`--lote`**: desloca a faixa de `id_coleta` (`lote * 1.000.000 + id_registro`), separando
   ondas de coleta. Sem `--lote`, reenviar o mesmo comando é idempotente de propósito.

## Evidências

### Rajada: 20 registros sem intervalo

```
ANTES  | telemetria: 1020 | scores: 1020 | alertas: 13
Resumo: 20 enviados | 20 aceitos | 0 já registrados | 0 rejeitados pela API | 0 falhas de rede
DEPOIS | telemetria: 1040 | scores: 1040 | alertas: 23
sem score: 0        ← toda entrada válida recebeu score
```

### Reenvio da mesma coleta (idempotência)

```
Resumo: 20 enviados | 0 aceitos | 20 já registrados | 0 rejeitados pela API | 0 falhas de rede
EQ-GO-0037 -> coleta já registrada (Coleta 19 já registrada (id_registro 1039))
```

Total de telemetria inalterado (1040) e nenhum score duplicado.

### Coleta pelo operador (RBAC) em um lote novo

```
python src/api/simulador_telemetria.py --n 3 --interval 0 --role operador \
       --equipamento EQ-MT-0023 --lote 1
EQ-MT-0023 -> 81 (Crítico) | predito 55 (Alto) | alerta SIM
EQ-MT-0023 -> 58 (Alto)   | predito 33 (Médio) | alerta NÃO
EQ-MT-0023 -> 100 (Crítico)| predito 81 (Crítico) | alerta SIM
Resumo: 3 enviados | 3 aceitos | 0 já registrados | 0 rejeitados pela API | 0 falhas de rede

coletas do lote 1: 3 | telemetria total: 1043 | scores: 1043 | sem score: 0 | duplicados equip+instante: 0
```

### API fora do ar

```
python src/api/simulador_telemetria.py --n 2 --base-url http://127.0.0.1:9999
API inacessível em http://127.0.0.1:9999/api/v1 — ConnectError: [WinError 10061] ...
exit code: 1
```

### Payload fora do padrão (pytest)

Fora de faixa, fora do domínio, coordenada impossível, contagem negativa e campo obrigatório
ausente: **422 em todos, com zero registros gravados** (`test_payload_malformado_e_recusado_sem_gravar`,
`test_payload_sem_campo_obrigatorio_e_recusado`).

### Consistência (pytest)

- `test_rajada_de_envios_persiste_tudo_com_score`: 15 envios → 15 registros e 15 scores.
- `test_coleta_reenviada_nao_duplica_dado`: 409, 1 registro, 1 score.
- `test_coleta_sem_id_explicito_continua_aceitando_envios`: sem `id_coleta`, dois envios = duas medições.
- Simulador: retry em 5xx, retry em timeout, desistência com motivo após as tentativas, renovação
  de token no 401, `id_coleta` no payload e `--equipamento`.

## Decisões

- **`limit` do histórico** validado pela #2 (1-1000): o dashboard pede o teto aceito; acima disso a
  API devolve 422 (regressão encontrada e corrigida na #4).
- **Coleta sem `id_coleta` continua permitida**: coletores simples (ou testes manuais) não são
  obrigados a declarar identidade; o preço é não haver deduplicação para eles.
- **409, não 200**: reenviar a mesma coleta é erro do cliente, não sucesso silencioso — a resposta
  traz o registro que já existe para o coletor reconciliar.
