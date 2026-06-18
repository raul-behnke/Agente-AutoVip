"""Smoke test for the Agno-native Amanda agent.

Skipped if OPENAI_API_KEY/settings.openai_api_key is unset.
"""
from __future__ import annotations

import asyncio
import os
import sys


async def _main() -> int:
    if not os.environ.get("OPENAI_API_KEY") and not _has_settings_key():
        print("skip: OPENAI_API_KEY not set")
        return 0

    from app.amanda.agent import get_agent
    from app.amanda.schemas import TurnReply
    from app.amanda.state_schema import default_state

    agent = get_agent()
    result = await agent.arun(
        input="Oi, gostaria de info sobre um HB20",
        session_id="test-smoke-agno-001",
        user_id="test-smoke-agno-001",
        session_state=default_state(),
    )
    print("Amanda response:")
    if not isinstance(result.content, TurnReply):
        print(f"unexpected content: {result.content!r}")
        return 1
    for i, bubble in enumerate(result.content.bubbles, 1):
        print(f"  [{i}] {bubble.text}")
    return 0


def _has_settings_key() -> bool:
    try:
        from app.config import settings

        return bool(settings.openai_api_key)
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
