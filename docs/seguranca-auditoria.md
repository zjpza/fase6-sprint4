# Segurança e auditoria — Sprint 4 (issue #6)

Consolidação da camada de segurança para uso real: segredo de assinatura fora do código, tokens
com expiração validada, escrita resistente a entrada maliciosa e uma trilha de auditoria que
registra não só acessos, mas **o que o sistema decidiu**.

## O que estava errado

| Onde | Comportamento na Sprint 3 |
|------|---------------------------|
| `src/security/auth.py:16-25` | Sem `JWT_SECRET_KEY`, assinava com a constante `agrorisk-dev-secret-change-me-32b` — **segredo versionado no repositório** (achado B10): qualquer pessoa com o código podia forjar um token de gestor |
| `.env.example` | Publicava o mesmo segredo de desenvolvimento como valor de exemplo |
| `src/security/audit_logger.py` / rotas | A trilha registrava acesso (`login`, `listar_*`, `receber_telemetria`), mas **não a decisão**: score gerado, alerta emitido e fatores ficavam só nas tabelas de domínio |
| — | Não havia consulta à trilha: o dado existia no banco e não era legível pela API |

## O que mudou

1. **Segredo resolvido, nunca embutido** (`security.auth._resolver_secret`): variável de ambiente →
   `.env` da raiz (via `python-dotenv`) → **segredo aleatório por processo** com aviso no log.
   Sem `JWT_SECRET_KEY`, cada reinício da API invalida os tokens emitidos antes — o preço de não
   existir segredo padrão conhecido.
2. **`.env.example` sanitizado**: só placeholder e a instrução para gerar um segredo de 32+ bytes.
3. **Decisão registrada na auditoria**: cada telemetria processada grava `decisao_risco` com
   `score_regra`, `nivel_regra`, `score_modelo`, `nivel_modelo`, `alerta` (decisão da regra),
   `divergente` e `fatores` — a trilha responde "quem acessou, quando e o que o sistema decidiu".
4. **`GET /api/v1/auditoria`** (Gestor de Frota e Analista; operador recebe 403): lista os eventos
   com usuário, ação, recurso, equipamento/registro, IP e detalhes, com filtro por `acao` e
   paginação de 1 a 1000. A própria consulta é auditada (`listar_auditoria`).
5. **Escrita íntegra**: além das validações Pydantic, CHECK/FK e do gatilho de consistência já
   existentes, um teste cobre tentativa de injeção no identificador do equipamento.

## Evidências

### Trilha de auditoria (consulta real pelo analista)

```
GET /api/v1/auditoria?acao=decisao_risco&limit=2   (ricardo@sompo.local)

2026-09-12T19:33:20 | Carlos Silva | decisao_risco |
  score_regra=58 nivel_regra=Alto score_modelo=33 nivel_modelo=Médio alerta=1 divergente=1
  fatores=velocidade_operacao_kmh,faixa_proximidade_encoded,historico_incidentes
2026-09-12T19:33:13 | Carlos Silva | decisao_risco |
  score_regra=100 nivel_regra=Crítico score_modelo=84 nivel_modelo=Crítico alerta=1 divergente=0
  fatores=umidade_solo_pct,faixa_proximidade_encoded,tipo_solo_encoded
ip registrado: 127.0.0.1
```

`alerta=` é a decisão da **regra** (fonte única) e `divergente=` sinaliza que regra e modelo
classificaram o registro em níveis diferentes — o caso ambíguo que o auditor precisa ver.
No exemplo, o primeiro registro é um alerta Alto da regra que o modelo classificaria como
Médio: na Sprint 3 esse alerta apareceria com `alerta=0` e nunca entraria no histórico.

### Segredo

```
python -c "import sys; sys.path.insert(0,'src'); import security.auth as a; print(len(a.SECRET_KEY))"
RuntimeWarning: JWT_SECRET_KEY não definida — usando segredo aleatório só deste processo...
43                     ← segredo efêmero, não a constante antiga
```

### Testes que travam o comportamento

| Teste | Garante |
|---|---|
| `test_token_expirado_e_recusado` | Token vencido → 401 "expirado" (expiração validada) |
| `test_token_com_assinatura_de_outro_segredo_e_recusado` | Token forjado com outro segredo → 401 "inválido" |
| `test_segredo_nao_fica_embutido_no_codigo` | Sem env, o segredo é aleatório e ≠ do default antigo |
| `test_identificador_com_sql_nao_afeta_o_banco` | `'; DROP TABLE telemetria; --` no id do equipamento → 422 e tabela intacta |
| `test_decisao_de_risco_fica_na_auditoria` | A decisão (scores, alerta, fatores) entra na trilha |
| `test_auditoria_consultavel_para_gestor_e_analista` | Consulta legível, filtro por ação funcionando |
| `test_operador_nao_acessa_a_trilha_de_auditoria` | RBAC da trilha (403 para operador) |
| `test_alerta_do_historico_segue_a_regra_mesmo_divergindo` | O alerta do histórico segue a regra (fonte única) com `divergente=` coerente na trilha |

**65 → 72 testes nesta issue; suite atual: 80 testes passando.**

## Decisões

- **Segredo efêmero em vez de recusa a subir**: a API continua funcionando sem configuração para
  avaliação/demo (o avaliador não precisa criar `.env`), mas sem credencial conhecida. Quem quiser
  tokens estáveis entre reinícios define `JWT_SECRET_KEY` no `.env`.
- **Senhas de demonstração continuam documentadas** no README e no dashboard: são três usuários
  fictícios semeados com hash bcrypt em `02_seed_data.sql`, criados para a avaliação — o que a
  issue pede é que *segredo* não fique no código, e isso vale para o segredo de assinatura.
- **Trilha em tabela própria, não em arquivo de log**: já existia (`auditoria`), com FK para
  usuário/equipamento/registro; ampliar o conteúdo foi mais barato e mais auditável que trocar o
  mecanismo.
- **A tela de auditoria no dashboard fica para a #7** — a API já entrega os eventos; a #7 monta os
  relatórios por perfil.
