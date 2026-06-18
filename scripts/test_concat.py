"""Lightweight runnable test for orchestrator/concat.py."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import transcription  # noqa: E402
from app.orchestrator import concat  # noqa: E402


async def _fake_transcribe(url: str) -> str:
    return "[transcrito]"


def main() -> int:
    # Monkey-patch transcribe
    transcription.transcribe = _fake_transcribe  # type: ignore[assignment]
    concat.transcription.transcribe = _fake_transcribe  # type: ignore[assignment]

    # Fixture: GHL returns newest-first typically — mix order
    messages = [
        # newest first
        {"id": "m5", "direction": "inbound", "dateAdded": "2026-05-28T10:05:00Z",
         "body": "", "attachments": [
             {"url": "https://cdn.example.com/pic1.jpg"},
             {"url": "https://cdn.example.com/pic2.jpg"},
         ]},
        {"id": "m4", "direction": "inbound", "dateAdded": "2026-05-28T10:04:00Z",
         "body": "", "attachments": [{"url": "https://cdn.example.com/voice.ogg"}]},
        {"id": "m3", "direction": "inbound", "dateAdded": "2026-05-28T10:03:00Z",
         "body": "oi, tudo bem?", "attachments": []},
        {"id": "m2", "direction": "outbound", "dateAdded": "2026-05-28T10:02:00Z",
         "body": "Olá! Sou a Amanda.", "attachments": []},
        {"id": "m1", "direction": "inbound", "dateAdded": "2026-05-28T10:01:00Z",
         "body": "oi", "attachments": []},
        {"id": "m0", "direction": "outbound", "dateAdded": "2026-05-28T10:00:00Z",
         "body": "menu inicial", "attachments": []},
    ]

    pending = concat.extract_pending_inbounds(messages)
    ok = True

    ids = [p["id"] for p in pending]
    if ids != ["m3", "m4", "m5"]:
        print(f"FAIL: expected [m3, m4, m5] got {ids}")
        ok = False
    else:
        print(f"PASS: extract returned {ids}")

    combined, photo_count = asyncio.run(concat.build_turn_input(pending))
    print(f"combined={combined!r}")
    print(f"photo_count={photo_count}")

    if "oi, tudo bem?" not in combined:
        print("FAIL: text missing in combined")
        ok = False
    if "[transcrito]" not in combined:
        print("FAIL: transcript missing in combined")
        ok = False
    if "[Cliente enviou 2 foto(s)]" not in combined:
        print("FAIL: photos marker missing in combined")
        ok = False
    if photo_count != 2:
        print(f"FAIL: photo_count expected 2 got {photo_count}")
        ok = False

    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
