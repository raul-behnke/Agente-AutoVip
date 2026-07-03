"""Post-hook enforce_bubbles — contrato de bolhas."""
from __future__ import annotations

from types import SimpleNamespace

from app.amanda.hooks import enforce_bubbles
from app.amanda.schemas import Bubble, TurnReply


def _run(content, state=None):
    ro = SimpleNamespace(content=content)
    rc = SimpleNamespace(session_state=state or {})
    enforce_bubbles(rc, ro)
    return ro.content


def test_trims_to_three_bubbles():
    reply = TurnReply(bubbles=[Bubble(text=f"b{i}") for i in range(4)])
    out = _run(reply)
    assert len(out.bubbles) == 3


def test_question_only_in_last_bubble():
    # Duas bolhas-pergunta → o pipeline colapsa mantendo só a ÚLTIMA pergunta
    # (bolhas-pergunta anteriores são descartadas). Invariante: no máx. 1 "?".
    reply = TurnReply(bubbles=[Bubble(text="tudo bem?"), Bubble(text="e ai?")])
    out = _run(reply)
    assert sum("?" in b.text for b in out.bubbles) == 1
    assert out.bubbles[-1].text.endswith("?")


def test_string_concat_json_recovered():
    s = '{"bubbles":[{"text":"oi"}]}{"bubbles":[{"text":"qual seu nome?"}]}'
    out = _run(s)
    assert isinstance(out, TurnReply)
    assert [b.text for b in out.bubbles] == ["oi", "qual seu nome?"]


def test_plain_string_fallback_single_bubble():
    # Fallback de string crua + estado vazio: o pipeline mantém o texto e ANEXA
    # a próxima pergunta do funil (mantém a qualificação viva).
    out = _run("texto solto sem json")
    assert isinstance(out, TurnReply)
    assert out.bubbles[0].text == "texto solto sem json"
    assert out.bubbles[-1].text.endswith("?")


def test_valid_single_bubble_untouched():
    reply = TurnReply(bubbles=[Bubble(text="quer agendar?")])
    out = _run(reply)
    assert out.bubbles[0].text == "quer agendar?"


# --- anti-eco (papagaio) ---

def _state(**dotted):
    from app.amanda.state_schema import ensure_keys, set_dotted
    st = ensure_keys({})
    for k, v in dotted.items():
        set_dotted(st, k.replace("__", "."), v)
    return st


def test_echo_data_bubble_dropped():
    st = _state(**{"troca__modelo": "Gol"})
    reply = TurnReply(bubbles=[
        Bubble(text="Entendi o carrinho, um Gol 2001 com 210 mil km."),
        Bubble(text="Ele está quitado ou financiado?"),
    ])
    out = _run(reply, st)
    texts = [b.text for b in out.bubbles]
    assert texts == ["Ele está quitado ou financiado?"]


def test_echo_leading_sentence_stripped_keeps_rest():
    st = _state(**{"lead__cidade": "Joinville"})
    reply = TurnReply(bubbles=[Bubble(text="Show, Joinville! Sou da equipe Auto Vip.")])
    out = _run(reply, st)
    assert out.bubbles[0].text == "Sou da equipe Auto Vip."


def test_rapport_without_data_preserved():
    # empatia/rapport sem dado NÃO é eco — deve ficar
    st = _state(**{"intencao": "troca"})
    reply = TurnReply(bubbles=[
        Bubble(text="Legal que quer trocar."),
        Bubble(text="Qual o modelo do seu atual?"),
    ])
    out = _run(reply, st)
    texts = [b.text for b in out.bubbles]
    assert "Legal que quer trocar." in texts


def test_echo_never_empties_response():
    # bolha única que é puro eco → não esvazia (segurança)
    st = _state(**{"lead__nome": "Raul"})
    reply = TurnReply(bubbles=[Bubble(text="Valeu, Raul.")])
    out = _run(reply, st)
    assert len(out.bubbles) >= 1 and out.bubbles[0].text
