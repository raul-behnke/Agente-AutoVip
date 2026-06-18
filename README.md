# Amanda — Auto Vip Agent

Agente WhatsApp (Agno + FastAPI + GHL) para a Auto Vip.

## Pré-requisitos

- Docker + Docker Compose
- Python 3.11+
- [ngrok](https://ngrok.com/) (para expor webhook ao GHL em dev)

## Quick start

```bash
# 1. Configurar env
cp .env.example .env
# Edite .env e preencha OPENAI_API_KEY (e GHL_PIT se ainda não estiver)

# 2. Subir Postgres (pgvector)
docker compose up -d

# 3. Instalar pacote no venv
source .venv/bin/activate
pip install -e .

# 4. Rodar FastAPI
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Expor via ngrok
ngrok http 8000
```

Health check: `curl http://localhost:8000/health` → `{"status":"ok"}`.

## Webhook GHL

Configure o Workflow do GHL para POSTar em:

```
https://<seu-ngrok>.ngrok-free.app/webhook/inbound/<WEBHOOK_TOKEN>
```

Onde `WEBHOOK_TOKEN` vem do `.env`.

**Importante:** o Workflow do GHL precisa enviar payload com `contact_id` ou
`contactId` no body (também aceita `contact.id` ou `customData.contact_id`).
Sem isso o endpoint responde `{"ok": false, "reason": "no contact_id"}` em
200 (devolver 4xx faz o GHL retentar).

## Estrutura

- `app/` — código da aplicação (FastAPI, agente Agno, cliente GHL, orquestrador).
- `plan/` — specs, plano de fases, correções.
- `logs/` — saída rotativa do loguru (10MB / 7 dias).
- `docker-compose.yml` — Postgres 16 + pgvector local.
