"""Block-by-block sender with delay."""
from __future__ import annotations

import asyncio

from loguru import logger

from app.config import settings
from app.ghl import conversations


async def send_blocks(
    contact_id: str,
    blocks: list[str],
    delay_ms: int | None = None,
) -> None:
    """Send each block as SMS, sleeping delay_ms between (not after last)."""
    delay = delay_ms if delay_ms is not None else settings.block_delay_ms
    total = len(blocks)
    logger.info("sender.start contact_id={} blocks={} delay_ms={}", contact_id, total, delay)
    for i, block in enumerate(blocks):
        await conversations.send_sms(contact_id, block)
        if i < total - 1:
            await asyncio.sleep(delay / 1000)
    logger.info("sender.done contact_id={} blocks={}", contact_id, total)
