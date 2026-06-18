Você é o agente de engenharia responsável pelo repositório `zaf-autovip` (agente "Amanda", Auto Vip), em produção na VPS2 (147.79.87.179, container autovip_app_prod).

CONTEXTO
A ZOI constrói o ZOI Performance Hub (telemetria central operacional/financeira/comercial). Produza o arquivo PLANO_ADEQUACAO_TELEMETRIA_AUTOVIP.md adequando ESTE agente para alimentar o Hub. Apenas o plano — sem implementar código agora.

FATOS CONFIRMADOS DA SUA ARQUITETURA
- Stack: Python 3.11 + FastAPI. Docker Compose + Nginx + Certbot. Domínio autovip.appzoi.com.br.
- Banco: PostgreSQL 16 (pgvector). 2 tabelas Agno: `amanda_sessions_v2` (session_state JSONB) + `amanda_memories_v2` (ociosa). Sem models próprios; schema gerido pelo Agno.
- IA: Agno (agno.agent.Agent), 8 tools. Modelos: gpt-4.1-mini (temp 0.6) + whisper-1.
- CRM: GHL via PIT token. Contacts/conversations/calendars/custom fields/tags. SEM Opportunities/Pipeline.
- Logs: loguru → logs/amanda.log (TEXTO não estruturado, rotação 10MB/7d) + stdout.
- Telemetria: Prometheus /metrics (12 métricas), incluindo amanda_llm_tokens_total{kind} e amanda_llm_cost_usd_total.

PARTICULARIDADE QUE TE DIFERENCIA (você JÁ tem base financeira — mas imatura)
- VOCÊ JÁ CAPTURA TOKENS: `runtime.py::_record_llm_cost` lê result.metrics.input_tokens/output_tokens (RunOutput do Agno) → Prometheus.
- VOCÊ JÁ CALCULA CUSTO: fórmula em runtime.py:45 → custo = (input/1e6)*0.40 + (output/1e6)*1.60. MAS:
  * Preço HARDCODED ($0.40/$1.60) → erro silencioso se trocar modelo.
  * Custo é AGREGADO GLOBAL (counter Prometheus), NÃO atribuível por conversa/lead.
  * Efêmero (zera no restart, sem scraper/retenção garantidos no repo).
  * total_tokens não exposto. request_id da OpenAI não capturado.

GAPS CRÍTICOS A RESOLVER
1. Tokens/custos NÃO PERSISTIDOS (só Prometheus em memória) → sem histórico financeiro.
2. Custo NÃO atribuível por conversa/lead/mensagem.
3. Custo do WHISPER não contabilizado.
4. Preço hardcoded → migrar para tabela `pricing` por modelo.
5. SEM Opportunities/Pipeline → comercial cego.
6. Logs em TEXTO loguru → migrar para JSON (loguru serialize=True) para ingestão.
7. conversationId obtido em runtime mas NÃO persistido.
8. Sem tabela relacional de eventos (estado é JSONB monolítico).
9. amanda_qualificados_total conta por turno (pode duplicar mesmo lead).
10. Repo SEM .git na VPS (rastreabilidade frágil) — registrar como risco.

O QUE O PLANO DEVE CONTER

1. SITUAÇÃO ATUAL — destacar que já existe captura de tokens + fórmula de custo (vantagem real sobre a frota).

2. GAPS — Operacional / Financeiro / Comercial.

3. ADEQUAÇÕES NECESSÁRIAS — Banco | Logs | Tokens | Custos | Whisper | CRM | Oportunidades.
   - Tokens: persistir result.metrics por turno COM contact_id + conversation_id + model + request_id.
   - Custos: substituir preço hardcoded por tabela pricing; incluir Whisper.
   - Logs: serialize=True (JSON).

4. ESTRATÉGIA DE INTEGRAÇÃO — você tem Postgres: recomende tabela de eventos lida pelo coletor do Hub; manter Prometheus para tempo real.

5. EVENTOS RECOMENDADOS — mapear ao código real:
   CONVERSATION_STARTED, CONVERSATION_COMPLETED, HANDOFF_CREATED, APPOINTMENT_CREATED, FOLLOWUP_STARTED, FOLLOWUP_FINISHED, CONVERSATION_ABANDONED, LLM_CALL, WHISPER_TRANSCRIPTION.
   Você já tem lógica de handoff/agendamento/reopen — aproveite. Marcar follow-up real como inexistente (só há reopen 24h).

6. PLANO DE EXECUÇÃO — Fase 1 (persistir LLM_CALL por conversa + pricing + Whisper), Fase 2 (eventos + logs JSON + dedup qualificados), Fase 3 (Opportunities GHL).

7. RESUMO EXECUTIVO.

8. SCORE DE ADERÊNCIA — atual (baseline ~5,0/10) e projetado.

REGRA: cite arquivos reais (runtime.py, app/metrics.py, app/amanda/agent.py). Nada genérico.
