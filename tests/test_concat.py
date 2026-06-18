"""extract_pending_inbounds — burst aggregation + filtro de atividades."""
from __future__ import annotations

from app.orchestrator.concat import extract_pending_inbounds


def _msg(ts, direction, body="x", type=20):
    return {"dateAdded": ts, "direction": direction, "body": body, "type": type}


def test_inbound_after_last_outbound_returned():
    msgs = [
        _msg("2026-06-10T10:00:00Z", "outbound"),
        _msg("2026-06-10T10:05:00Z", "inbound", "oi"),
    ]
    out = extract_pending_inbounds(msgs)
    assert [m["body"] for m in out] == ["oi"]


def test_inbound_before_last_outbound_empty():
    msgs = [
        _msg("2026-06-10T10:00:00Z", "inbound", "oi"),
        _msg("2026-06-10T10:05:00Z", "outbound", "resposta"),
    ]
    assert extract_pending_inbounds(msgs) == []


def test_activity_records_ignored():
    msgs = [
        _msg("2026-06-10T10:00:00Z", "outbound", "Olá"),
        _msg("2026-06-10T10:01:00Z", "inbound", "quero info"),
        _msg("2026-06-10T10:02:00Z", "outbound", "Opportunity created", type=28),
    ]
    # a atividade type=28 não conta como outbound real → inbound continua pendente
    out = extract_pending_inbounds(msgs)
    assert [m["body"] for m in out] == ["quero info"]


def test_no_outbound_returns_all_inbounds():
    msgs = [
        _msg("2026-06-10T10:00:00Z", "inbound", "a"),
        _msg("2026-06-10T10:01:00Z", "inbound", "b"),
    ]
    out = extract_pending_inbounds(msgs)
    assert [m["body"] for m in out] == ["a", "b"]


def test_burst_multiple_inbounds_after_outbound_ordered():
    msgs = [
        _msg("2026-06-10T10:00:00Z", "outbound", "pergunta"),
        _msg("2026-06-10T10:03:00Z", "inbound", "segunda"),
        _msg("2026-06-10T10:02:00Z", "inbound", "primeira"),
    ]
    out = extract_pending_inbounds(msgs)
    assert [m["body"] for m in out] == ["primeira", "segunda"]
