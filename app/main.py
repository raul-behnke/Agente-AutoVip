"""FastAPI entrypoint for the Amanda agent (Agno-native)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from loguru import logger

from app import metrics, webhook
from app.amanda import runtime as amanda_runtime
from app.amanda.agent import get_agent
from app.ghl.client import close_client, get_client
from app.logging import setup_logging

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup: initializing httpx client + Amanda agent")
    get_client()
    get_agent()  # warm singleton + db schema bootstrap
    # Telemetria persistida (Hub): cria tabelas llm_calls/agent_events/pricing
    # e faz seed do preço dos modelos. Tolerante a falha — não bloqueia startup.
    from app.telemetry import init_telemetry_schema
    from app import pricing
    try:
        await asyncio.to_thread(init_telemetry_schema)
        await asyncio.to_thread(pricing.seed_pricing)
    except Exception as e:
        logger.error("startup.telemetry_init_failed err={}", e)
    from app.amanda import tools as amanda_tools
    await amanda_tools.refresh_faq_from_ghl()  # FAQ canônico GHL (fallback local)
    yield
    logger.info("shutdown: waiting active tasks (timeout=30s)")
    tasks = [t for t in amanda_runtime.active_tasks.values() if not t.done()]
    if tasks:
        try:
            await asyncio.wait(tasks, timeout=30)
        except Exception as e:
            logger.warning("shutdown: error awaiting tasks err={}", e)
    await close_client()
    logger.info("shutdown: done")


app = FastAPI(title="Amanda", version="0.3.0", lifespan=lifespan)
app.include_router(webhook.router)

from app.export_router import router as export_router  # noqa: E402
app.include_router(export_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0", "engine": "agno"}


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    payload, content_type = metrics.render()
    return Response(content=payload, media_type=content_type)
