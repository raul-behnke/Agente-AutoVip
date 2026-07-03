"""Testes dos ajustes de qualificação da Amanda.

Cobre determinísticamente (sem LLM):
  - léxico: "carrinho" nunca sai na bolha (vira "carro"/"carros");
  - frase exata do CPF na sugestão do funil;
  - "só troca na entrada" (forma_pagamento_diferenca=apenas_troca) NÃO puxa
    funil de financiamento (sem CPF/entrada/parcela);
  - ordem fixa da troca + anti-repetição de pergunta já feita;
  - regras de consultor (Ramon) e léxico presentes nas instruções.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.amanda.hooks import enforce_bubbles
from app.amanda.instructions import INSTRUCTIONS
from app.amanda.schemas import Bubble, TurnReply
from app.amanda.state_schema import (
    ensure_keys,
    funnel_for,
    missing_fields,
    set_dotted,
)
from app.amanda.tools import _SUGESTOES, pick_next_question


def _run(content, state=None):
    ro = SimpleNamespace(content=content)
    rc = SimpleNamespace(session_state=state or {})
    enforce_bubbles(rc, ro)
    return ro.content


# --------------------------------------------------------------------------
# Léxico: nunca "carrinho"
# --------------------------------------------------------------------------
def test_carrinho_virou_carro():
    out = _run(TurnReply(bubbles=[Bubble(text="Que carrinho legal!")]))
    assert "carrinho" not in out.bubbles[0].text.lower()
    assert "carro" in out.bubbles[0].text.lower()


def test_carrinhos_plural_virou_carros():
    out = _run(TurnReply(bubbles=[Bubble(text="Temos vários carrinhos aqui")]))
    assert "carrinho" not in out.bubbles[0].text.lower()
    assert "carros" in out.bubbles[0].text.lower()


def test_carrinho_capitalizado_preserva_caixa():
    out = _run(TurnReply(bubbles=[Bubble(text="Carrinho novo?")]))
    txt = out.bubbles[0].text
    assert txt.startswith("Carro")
    assert "carrinho" not in txt.lower()


def test_carro_normal_intocado():
    out = _run(TurnReply(bubbles=[Bubble(text="Qual o modelo do seu carro?")]))
    assert out.bubbles[0].text == "Qual o modelo do seu carro?"


# --------------------------------------------------------------------------
# Frase exata do CPF
# --------------------------------------------------------------------------
def test_sugestao_cpf_frase_exata():
    esperado = (
        "Certo, Eu vou fazer uma simulação de parcela pra você e conseguir a "
        "melhor proposta. Me passa seu CPF e data de nascimento por gentileza"
    )
    assert _SUGESTOES["financiamento.cpf"] == esperado


# --------------------------------------------------------------------------
# "Só troca na entrada" — apenas_troca NÃO pede financiamento
# --------------------------------------------------------------------------
def _troca_state(**troca):
    st = ensure_keys({})
    st["intencao"] = "troca"
    st["lead"]["nome"] = "Raul"
    st["lead"]["cidade"] = "Itajaí"
    for k, v in troca.items():
        set_dotted(st, f"troca.{k}", v)
    return st


def test_apenas_troca_nao_puxa_financiamento():
    st = _troca_state(
        modelo="Gol", ano=2015, km=90000,
        quitado_ou_financiado="quitado", fotos_solicitadas=True,
        forma_pagamento_diferenca="apenas_troca",
    )
    funil = funnel_for(st)
    assert "financiamento.cpf" not in funil
    assert "financiamento.entrada" not in funil
    assert "financiamento.parcela_desejada" not in funil
    # coleta completa (nenhum campo de financiamento pendente)
    assert missing_fields(st) == []


def test_financiamento_diferenca_puxa_cpf():
    st = _troca_state(
        modelo="Gol", ano=2015, km=90000,
        quitado_ou_financiado="quitado", fotos_solicitadas=True,
        forma_pagamento_diferenca="financiamento",
    )
    funil = funnel_for(st)
    assert "financiamento.cpf" in funil
    assert "financiamento.entrada" in funil


# --------------------------------------------------------------------------
# Ordem fixa da troca + anti-repetição
# --------------------------------------------------------------------------
def test_ordem_troca_modelo_primeiro():
    st = _troca_state()
    _missing, target, _sug = pick_next_question(st)
    assert target == "troca.modelo"


def test_ordem_troca_avanca_para_ano_apos_modelo():
    st = _troca_state(modelo="Gol")
    _missing, target, _sug = pick_next_question(st)
    assert target == "troca.ano"


def test_ordem_troca_sequencia_completa():
    st = _troca_state()
    vistos = []
    # simula preencher na ordem que o planner pedir
    ordem_campos = {
        "troca.modelo": "Gol", "troca.ano": 2015, "troca.km": 90000,
        "troca.quitado_ou_financiado": "quitado",
        "troca.fotos_solicitadas": True,
        "troca.forma_pagamento_diferenca": "apenas_troca",
    }
    for _ in range(6):
        _m, target, _s = pick_next_question(st)
        if target is None:
            break
        vistos.append(target)
        set_dotted(st, target, ordem_campos[target])
    assert vistos == [
        "troca.modelo", "troca.ano", "troca.km",
        "troca.quitado_ou_financiado", "troca.fotos_solicitadas",
        "troca.forma_pagamento_diferenca",
    ]


def test_anti_repeticao_pula_campo_recente():
    # km é o primeiro faltante mas foi perguntado nos últimos turnos → pula
    st = _troca_state(modelo="Gol", ano=2015)
    st["last_asked"] = ["troca.km", "troca.km", "troca.km"]
    _missing, target, _sug = pick_next_question(st)
    assert target != "troca.km"
    assert target == "troca.quitado_ou_financiado"


# --------------------------------------------------------------------------
# Instruções contêm as regras novas
# --------------------------------------------------------------------------
def test_instrucoes_citam_ramon():
    assert "Ramon" in INSTRUCTIONS


def test_instrucoes_proibem_carrinho():
    assert "carrinho" in INSTRUCTIONS.lower()  # menciona a proibição


def test_instrucoes_tem_frase_cpf():
    assert "simulação de parcela" in INSTRUCTIONS


def test_instrucoes_tem_apenas_troca():
    assert "apenas_troca" in INSTRUCTIONS
