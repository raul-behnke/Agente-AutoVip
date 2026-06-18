"""Application settings loaded from .env via pydantic-settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # GHL
    ghl_pit: str = ""
    ghl_location_id: str = ""
    ghl_base_url: str = "https://services.leadconnectorhq.com"

    # Users
    sender_user_id: str = ""
    ramon_user_id: str = ""

    # Calendars
    cal_presencial_id: str = ""
    cal_video_id: str = ""

    # Pipeline / Opportunities (Fase 3 — camada comercial). Se vazio, o
    # vínculo de oportunidade é pulado (best-effort, sem quebrar handoff).
    ghl_pipeline_id: str = ""
    ghl_pipeline_stage_id: str = ""

    # Custom values
    faq_custom_value_id: str = ""

    # Store
    loja_endereco: str = ""

    # Webhook
    webhook_token: str = ""

    # Export para o ZOI Performance Hub (PULL HTTP incremental). Secret
    # DEDICADO — distinto do webhook_token. Vazio = endpoint desativado (503).
    zoi_export_secret: str = ""
    export_table: str = "agent_events"

    # OpenAI
    openai_api_key: str = ""

    # DB
    database_url: str = "postgresql+psycopg://amanda:amanda@localhost:5434/amanda"

    # Behavior
    block_delay_ms: int = 2000


settings = Settings()
