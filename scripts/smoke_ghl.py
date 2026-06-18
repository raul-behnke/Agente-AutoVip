"""Smoke test for GHL client (read-only)."""
from __future__ import annotations

import argparse
import asyncio
import time
from pprint import pprint

from loguru import logger

from app.config import settings
from app.ghl import calendars, client, contacts, conversations, custom_values  # noqa: F401


async def run(contact_id: str | None) -> None:
    if not contact_id:
        print("set --contact-id to run live tests")
        return

    print(f"=== smoke against contact_id={contact_id} ===")

    conv_id: str | None = None
    try:
        conv_id = await conversations.search_conversation(contact_id)
        print(f"[ok] search_conversation -> {conv_id}")
    except Exception as e:
        logger.exception("search_conversation failed: {}", e)

    if conv_id:
        try:
            msgs = await conversations.get_messages(conv_id, limit=10)
            print(f"[ok] get_messages -> {len(msgs)} messages")
            if msgs:
                pprint(msgs[0])
        except Exception as e:
            logger.exception("get_messages failed: {}", e)

    if settings.faq_custom_value_id:
        try:
            val = await custom_values.get_custom_value(settings.faq_custom_value_id)
            print(f"[ok] get_custom_value(FAQ) -> {len(val)} chars")
        except Exception as e:
            logger.exception("get_custom_value failed: {}", e)
    else:
        print("[skip] FAQ_CUSTOM_VALUE_ID not set")

    if settings.cal_presencial_id:
        try:
            now_ms = int(time.time() * 1000)
            start_ms = now_ms + 60 * 60 * 1000
            end_ms = now_ms + 24 * 60 * 60 * 1000
            slots = await calendars.get_free_slots(settings.cal_presencial_id, start_ms, end_ms)
            print(f"[ok] get_free_slots -> keys={list(slots.keys())[:5]}")
        except Exception as e:
            logger.exception("get_free_slots failed: {}", e)
    else:
        print("[skip] CAL_PRESENCIAL_ID not set")

    print("[skip] write ops (send_sms, book_appointment) — add --write flag later")

    await client.close_client()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contact-id", dest="contact_id", default=None)
    args = parser.parse_args()
    asyncio.run(run(args.contact_id))


if __name__ == "__main__":
    main()
