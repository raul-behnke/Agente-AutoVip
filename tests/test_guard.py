"""Guard anti-alucinação de registrar_lead_info."""
from __future__ import annotations

from app.amanda.tools import _norm, _value_supported_by_msg


def test_norm_strips_accents_and_case():
    assert _norm("Joinville") == "joinville"
    assert _norm("São  Paulo") == "sao paulo"


def test_text_field_supported_substring():
    assert _value_supported_by_msg("lead.nome", "Raul", "meu nome é Raul")
    assert _value_supported_by_msg("lead.cidade", "Joinville", "sou de joinville mesmo")


def test_text_field_rejected_when_not_said():
    assert not _value_supported_by_msg("lead.nome", "Carlos", "meu nome é Raul")
    assert not _value_supported_by_msg("troca.modelo", "Civic", "tenho um onix")


def test_text_field_multiword_tokens():
    assert _value_supported_by_msg("troca.modelo", "Onix 2020", "vi o anuncio do onix 2020")


def test_numeric_field_digit_match():
    assert _value_supported_by_msg("troca.ano", "2020", "é de 2020")
    assert not _value_supported_by_msg("troca.ano", "2018", "é de 2020")


def test_cpf_digit_match_ignores_punctuation():
    assert _value_supported_by_msg("financiamento.cpf", "12345678900", "cpf 123.456.789-00")


def test_numeric_mil_multiplier():
    # lead diz "210mil km" → modelo grava 210000 — deve ser aceito
    assert _value_supported_by_msg("troca.km", "210000", "210mil km")
    assert _value_supported_by_msg("troca.km", "210000", "210 mil km")
    assert _value_supported_by_msg("troca.km", "50000", "uns 50k rodados")


def test_numeric_short_form_prefix():
    # lead diz "210", modelo expande pra 210000 → aceito via prefixo
    assert _value_supported_by_msg("troca.km", "210000", "tá com 210 rodados")


def test_numeric_milhao_entrada():
    assert _value_supported_by_msg("financiamento.entrada", "2000000", "dou 2 milhões de entrada")


def test_numeric_still_rejects_unrelated():
    assert not _value_supported_by_msg("troca.km", "180000", "210mil km")


def test_no_message_does_not_block():
    # ex.: teste direto / sem _last_user_msg → não bloqueia
    assert _value_supported_by_msg("lead.nome", "Raul", "")


def test_boolean_enum_fields_out_of_guard():
    assert _value_supported_by_msg("troca.fotos_solicitadas", True, "qualquer coisa")
    assert _value_supported_by_msg("intencao", "vista", "qualquer coisa")
