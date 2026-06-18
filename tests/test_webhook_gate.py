"""Gate de tag agente-ia + extração de contact_id."""
from __future__ import annotations

from app.webhook import _extract_contact_id, _parse_tags


def test_parse_tags_list():
    assert _parse_tags(["Agente-IA", "novo_lead"]) == {"agente-ia", "novo_lead"}


def test_parse_tags_csv():
    assert _parse_tags("agente-ia, aberto") == {"agente-ia", "aberto"}


def test_parse_tags_empty():
    assert _parse_tags(None) == set()
    assert _parse_tags(123) == set()


def test_gate_tag_present():
    assert "agente-ia" in _parse_tags(["agente-ia", "x"])


def test_gate_tag_absent():
    assert "agente-ia" not in _parse_tags(["novo_lead", "aberto"])


def test_extract_contact_id_variants():
    assert _extract_contact_id({"contact_id": "A"}) == "A"
    assert _extract_contact_id({"contactId": "B"}) == "B"
    assert _extract_contact_id({"contact": {"id": "C"}}) == "C"
    assert _extract_contact_id({"customData": {"contact_id": "D"}}) == "D"
    assert _extract_contact_id({"nope": 1}) is None
