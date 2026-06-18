"""Funil dinâmico + anti-repetição determinística."""
from __future__ import annotations

from app.amanda.state_schema import (
    default_state,
    ensure_keys,
    funnel_for,
    get_dotted,
    missing_fields,
    set_dotted,
)
from app.amanda.tools import pick_next_question


def _state(intencao=None):
    st = ensure_keys({})
    if intencao:
        st["intencao"] = intencao
    return st


def test_default_state_has_deflexao_counter():
    assert default_state()["counters"]["deflexao"] == 0


def test_ensure_keys_backfills_missing_subkeys():
    # state antigo sem o counter novo é retro-preenchido sem regredir dados
    old = {"lead": {"nome": "Raul"}, "counters": {"reopen": 2}}
    st = ensure_keys(old)
    assert st["lead"]["nome"] == "Raul"
    assert st["counters"]["reopen"] == 2
    assert st["counters"]["deflexao"] == 0


def test_funnel_base_only_without_intent():
    assert funnel_for(_state()) == ("lead.nome", "lead.cidade", "intencao")


def test_funnel_vista():
    f = funnel_for(_state("vista"))
    assert "vista_confirmado" in f and "financiamento.cpf" not in f


def test_funnel_financiamento_includes_cpf():
    f = funnel_for(_state("financiamento"))
    assert "financiamento.cpf" in f and "vista_confirmado" not in f


def test_funnel_troca_adds_financiamento_when_diff_financed():
    st = _state("troca")
    set_dotted(st, "troca.forma_pagamento_diferenca", "financiamento")
    f = funnel_for(st)
    assert "troca.modelo" in f and "financiamento.cpf" in f


def test_missing_shrinks_as_fields_fill():
    st = _state("vista")
    base = missing_fields(st)
    set_dotted(st, "lead.nome", "Raul")
    assert len(missing_fields(st)) == len(base) - 1


def test_get_set_dotted_roundtrip():
    st = default_state()
    set_dotted(st, "financiamento.cpf", "123")
    assert get_dotted(st, "financiamento.cpf") == "123"


def test_pick_next_question_advances_and_records():
    st = _state("financiamento")
    _, t1, s1 = pick_next_question(st)
    assert t1 == "lead.nome" and s1
    assert st["last_asked"][-1] == "lead.nome"


def test_pick_next_question_anti_repetition():
    # mesmo sem coletar o campo, não sugere o mesmo perguntado no turno anterior
    st = _state("financiamento")
    set_dotted(st, "lead.nome", "Raul")
    set_dotted(st, "lead.cidade", "Itajai")
    _, first, _ = pick_next_question(st)          # cpf
    _, second, _ = pick_next_question(st)         # deve pular cpf -> outro
    assert first != second


def test_pick_next_question_empty_when_complete():
    st = _state("vista")
    set_dotted(st, "lead.nome", "Raul")
    set_dotted(st, "lead.cidade", "Itajai")
    set_dotted(st, "vista_confirmado", True)
    missing, target, sug = pick_next_question(st)
    assert missing == [] and target is None and sug is None
