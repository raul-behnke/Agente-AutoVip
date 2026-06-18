"""Compatibility entrypoint for the current Agno runtime tests.

The old orchestrator test targeted the removed `app.agent.amanda` flow. Keep
this filename runnable for existing habits/scripts, but delegate to the
Agno-native runtime suite.
"""
from __future__ import annotations

import asyncio

from scripts.test_agno_runtime import main


if __name__ == "__main__":
    asyncio.run(main())
