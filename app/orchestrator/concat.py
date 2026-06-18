"""Extract inbound messages since last outbound, process attachments."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from loguru import logger

from app import transcription

_AUDIO_EXTS = (".ogg", ".oga", ".opus", ".mp3", ".m4a", ".wav", ".webm", ".mpeg", ".mpga", ".flac")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp")


@dataclass
class ProcessedMessage:
    id: str
    kind: Literal["text", "audio", "photos", "other"]
    text: str
    raw: dict


def _is_audio_attachment(att: str | dict) -> bool:
    s = (att if isinstance(att, str) else (att.get("url") or att.get("mime") or att.get("type") or "")).lower()
    if "audio/" in s:
        return True
    return any(s.split("?")[0].endswith(ext) for ext in _AUDIO_EXTS)


def _is_image_attachment(att: str | dict) -> bool:
    s = (att if isinstance(att, str) else (att.get("url") or att.get("mime") or att.get("type") or "")).lower()
    if "image/" in s:
        return True
    return any(s.split("?")[0].endswith(ext) for ext in _IMAGE_EXTS)


def _att_url(att: str | dict) -> str:
    if isinstance(att, str):
        return att
    return att.get("url") or ""


def _is_activity(msg: dict) -> bool:
    """GHL activity records (type >= 25: opportunity/appointment/invoice/etc.) are not real messages."""
    t = msg.get("type")
    return isinstance(t, int) and t >= 25


def extract_pending_inbounds(messages: list[dict]) -> list[dict]:
    """Return all inbound msgs after the last outbound, chronological order.

    If no outbound exists yet, return all inbounds.
    GHL returns newest-first typically; sort ascending by dateAdded first.
    Activity records (type >= 25) are ignored — they're not real conversation messages.
    """
    real_msgs = [m for m in messages if not _is_activity(m)]
    sorted_msgs = sorted(real_msgs, key=lambda m: m.get("dateAdded") or "")

    last_outbound_idx = -1
    for i, m in enumerate(sorted_msgs):
        if (m.get("direction") or "").lower() == "outbound":
            last_outbound_idx = i

    tail = sorted_msgs[last_outbound_idx + 1:]
    return [m for m in tail if (m.get("direction") or "").lower() == "inbound"]


_GHL_PLACEHOLDER_MARKERS = (
    "type message: audio",
    "type message: document",
    "type message: image",
    "type message: video",
    "✅ sent from another device",
    "forwarded",
)


def _clean_ghl_body(body: str) -> str:
    """Remove GHL transport metadata while preserving the lead's real text."""
    if not body:
        return ""
    lines = [line.rstrip() for line in body.replace("\r\n", "\n").split("\n")]
    cleaned: list[str] = []
    skip_next_message_label = False
    for line in lines:
        stripped = line.strip()
        low = stripped.lower()
        if low.startswith("source:"):
            continue
        if low == "✅ sent from another device ✅":
            continue
        if low == "message:":
            skip_next_message_label = True
            continue
        if skip_next_message_label and not stripped:
            continue
        skip_next_message_label = False
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _is_ghl_placeholder_body(body: str) -> bool:
    """GHL fills `body` with metadata strings like 'type message: audio\\n\\nSource: X' for media msgs."""
    low = _clean_ghl_body(body).lower()
    return any(m in low for m in _GHL_PLACEHOLDER_MARKERS)


async def process_inbound(
    msg: dict,
    *,
    contact_id: str | None = None,
    conversation_id: str | None = None,
) -> ProcessedMessage:
    msg_id = str(msg.get("id") or "")
    body = _clean_ghl_body((msg.get("body") or "").strip())
    attachments = msg.get("attachments") or []

    audio_atts = [a for a in attachments if _is_audio_attachment(a)]
    image_atts = [a for a in attachments if _is_image_attachment(a)]

    if body and not audio_atts and not image_atts and not _is_ghl_placeholder_body(body):
        return ProcessedMessage(id=msg_id, kind="text", text=body, raw=msg)

    if audio_atts:
        transcripts: list[str] = []
        for a in audio_atts:
            url = _att_url(a)
            if not url:
                continue
            try:
                t = await transcription.transcribe(
                    url, contact_id=contact_id, conversation_id=conversation_id
                )
                transcripts.append(t)
            except Exception as e:
                logger.error(f"transcribe failed msg_id={msg_id} url={url} err={e}")
                transcripts.append("[áudio não transcrito]")
        joined = "\n".join(transcripts)
        return ProcessedMessage(
            id=msg_id, kind="audio", text=f"[áudio transcrito]: {joined}", raw=msg
        )

    if image_atts:
        n = len(image_atts)
        return ProcessedMessage(
            id=msg_id, kind="photos", text=f"[Cliente enviou {n} foto(s)]", raw=msg
        )

    if body and not _is_ghl_placeholder_body(body):
        return ProcessedMessage(id=msg_id, kind="text", text=body, raw=msg)

    return ProcessedMessage(
        id=msg_id, kind="other", text="[Cliente enviou anexo não suportado]", raw=msg
    )


def format_history(messages: list[dict], pending: list[dict]) -> str:
    """Render prior conversation as 'Cliente:' / 'Amanda:' lines, excluding pending.

    History = all messages chronologically except the trailing pending inbounds.
    Attachments are noted without transcription (cost/latency).
    """
    pending_ids = {str(m.get("id") or "") for m in pending}
    real_msgs = [m for m in messages if not _is_activity(m)]
    sorted_msgs = sorted(real_msgs, key=lambda m: m.get("dateAdded") or "")
    lines: list[str] = []
    for m in sorted_msgs:
        if str(m.get("id") or "") in pending_ids:
            continue
        direction = (m.get("direction") or "").lower()
        speaker = "Amanda" if direction == "outbound" else "Cliente"
        body = _clean_ghl_body((m.get("body") or "").strip())
        attachments = m.get("attachments") or []
        if not body and attachments:
            if any(_is_audio_attachment(a) for a in attachments):
                body = "[áudio]"
            elif any(_is_image_attachment(a) for a in attachments):
                n = sum(1 for a in attachments if _is_image_attachment(a))
                body = f"[{n} foto(s)]"
            else:
                body = "[anexo]"
        if body:
            lines.append(f"{speaker}: {body}")
    return "\n".join(lines)


async def build_turn_input(
    pending: list[dict],
    *,
    contact_id: str | None = None,
    conversation_id: str | None = None,
) -> tuple[str, int]:
    """Process pending inbounds concurrently; return (combined_text, photo_count)."""
    if not pending:
        return "", 0
    processed = await asyncio.gather(
        *(
            process_inbound(m, contact_id=contact_id, conversation_id=conversation_id)
            for m in pending
        )
    )
    combined = "\n".join(p.text for p in processed if p.text)
    photo_count = sum(
        len([a for a in (p.raw.get("attachments") or []) if _is_image_attachment(a)])
        for p in processed if p.kind == "photos"
    )
    return combined, photo_count
