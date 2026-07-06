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
def test_cpf_duas_bolhas_colapsa_para_canonica():
    # Caso real do bug: paráfrase curta + canônica → 1 bolha só, a canônica.
    curta = Bubble(text="Me passa seu CPF e data de nascimento por gentileza.")
    canon = Bubble(text=_SUGESTOES["financiamento.cpf"])
    out = _run(TurnReply(bubbles=[curta, canon]))
    cpf_bolhas = [b for b in out.bubbles if "cpf" in b.text.lower()]
    assert len(cpf_bolhas) == 1
    assert cpf_bolhas[0].text == _SUGESTOES["financiamento.cpf"]


def test_cpf_parafrase_unica_vira_canonica():
    out = _run(TurnReply(bubbles=[Bubble(text="me passa seu CPF aí")]))
    cpf_bolhas = [b for b in out.bubbles if "cpf" in b.text.lower()]
    assert len(cpf_bolhas) == 1
    assert cpf_bolhas[0].text == _SUGESTOES["financiamento.cpf"]


def test_cpf_nao_anexa_pergunta_extra():
    # Estado com funil incompleto + só a bolha de CPF (sem "?") NÃO deve ganhar
    # uma pergunta de funil anexada depois.
    st = _troca_state(
        modelo="Gol", ano=2015, km=90000,
        quitado_ou_financiado="quitado", fotos_solicitadas=True,
        forma_pagamento_diferenca="financiamento",
    )
    out = _run(TurnReply(bubbles=[Bubble(text=_SUGESTOES["financiamento.cpf"])]), st)
    assert len(out.bubbles) == 1
    assert out.bubbles[0].text == _SUGESTOES["financiamento.cpf"]


def test_deflexao_parcela_removida_quando_lead_responde():
    # Amanda perguntou a parcela; lead respondeu com valor → deflexão indevida
    # deve ser removida, mantendo a próxima pergunta.
    st = ensure_keys({})
    st["last_asked"] = ["financiamento.parcela_desejada"]
    st["_last_user_msg"] = "No máximo 1300"
    out = _run(TurnReply(bubbles=[
        Bubble(text="Sobre o valor da parcela, quem confirma certinho é o consultor Ramon."),
        Bubble(text="Você já tem CNH?"),
    ]), st)
    textos = " ".join(b.text.lower() for b in out.bubbles)
    assert "quem confirma" not in textos
    assert any("cnh" in b.text.lower() for b in out.bubbles)


def test_deflexao_parcela_mantida_quando_lead_pergunta():
    # Lead PERGUNTOU o valor → deflexão é legítima, não remove.
    st = ensure_keys({})
    st["last_asked"] = ["financiamento.parcela_desejada"]
    st["_last_user_msg"] = "Quanto vai ficar a parcela?"
    out = _run(TurnReply(bubbles=[
        Bubble(text="Sobre o valor da parcela, quem confirma certinho é o consultor Ramon."),
    ]), st)
    assert any("quem confirma" in b.text.lower() for b in out.bubbles)


def test_primeiro_carro_nao_pede_cpf_primeiro():
    # primeiro_carro → funil financiamento, mas CPF é por ÚLTIMO; a 1ª pergunta
    # do financiamento é entrada, não CPF.
    st = ensure_keys({})
    st["intencao"] = "primeiro_carro"
    st["lead"]["nome"] = "Vitoria"; st["lead"]["cidade"] = "Joinville"
    _missing, target, _sug = pick_next_question(st)
    assert target == "financiamento.entrada"
    assert target != "financiamento.cpf"


def test_reassurance_golpe_nao_vira_canonica():
    # Bolha de reassurance que menciona CPF + golpe NÃO deve ser forçada à frase
    # canônica (senão destrói o tratamento da objeção).
    txt = ("Imagina, nada de golpe. Preciso do seu CPF só pra consultar a "
           "simulação direto com os bancos e trazer a melhor proposta.")
    out = _run(TurnReply(bubbles=[Bubble(text=txt)]))
    assert any("golpe" in b.text.lower() for b in out.bubbles)


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


def test_anti_repeticao_nao_pula_apos_uma_pergunta():
    # Campo perguntado 1x (não 2x) NÃO deve ser pulado — senão órfã a resposta
    # que o lead está dando agora (bug do CPF em produção).
    st = _troca_state(modelo="Gol", ano=2015, km=90000,
                      quitado_ou_financiado="quitado", fotos_solicitadas=True,
                      forma_pagamento_diferenca="financiamento")
    st["last_asked"] = ["financiamento.entrada"]  # perguntado 1x só
    _missing, target, _sug = pick_next_question(st)
    assert target == "financiamento.entrada"  # continua o foco, não pula


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


# --------------------------------------------------------------------------
# Tom natural: reconhecimento contextual sobrevive; eco literal é barrado
# --------------------------------------------------------------------------
def _st_modelo(modelo="Gol"):
    st = ensure_keys({})
    set_dotted(st, "troca.modelo", modelo)
    st["intencao"] = "troca"
    return st


def test_comentario_contextual_sobrevive():
    # "esse modelo é comum" NÃO é eco (não devolve o valor) → deve ficar.
    st = _st_modelo("Gol")
    out = _run(TurnReply(bubbles=[
        Bubble(text="Boa, esse modelo é bem comum na troca aqui."),
        Bubble(text="Ele tá com quantos km mais ou menos?"),
    ]), st)
    textos = [b.text for b in out.bubbles]
    assert "Boa, esse modelo é bem comum na troca aqui." in textos
    assert any("km" in t.lower() for t in textos)


def test_eco_valor_literal_ainda_barrado():
    # devolver o valor ("Gol 2001") continua sendo eco → removido.
    st = _st_modelo("Gol")
    out = _run(TurnReply(bubbles=[
        Bubble(text="Show, um Gol 2001!"),
        Bubble(text="Ele tá quitado?"),
    ]), st)
    textos = [b.text for b in out.bubbles]
    assert not any("2001" in t for t in textos)


def test_pergunta_offscript_trocada_por_funil():
    # "Ele é seu há quanto tempo?" não é do funil → trocada pela pergunta do
    # funil, mantendo a bolha de contexto anterior.
    st = _troca_state(modelo="Gol")  # próximo campo = troca.ano
    out = _run(TurnReply(bubbles=[
        Bubble(text="Boa, esse modelo sai bastante."),
        Bubble(text="Ele é seu há quanto tempo?"),
    ]), st)
    textos = [b.text for b in out.bubbles]
    assert not any("quanto tempo" in t.lower() for t in textos)
    assert any("ano" in t.lower() for t in textos)  # virou a pergunta do funil


def test_pergunta_offscript_porque_trocar():
    st = _troca_state(modelo="Gol")
    out = _run(TurnReply(bubbles=[Bubble(text="Por que você quer trocar?")]), st)
    assert not any("por que" in b.text.lower() for b in out.bubbles)


def test_nao_repergunta_km_ja_preenchido():
    # Lead deu modelo+km numa msg; modelo gravou os dois mas ainda perguntou km.
    # Guard troca pela próxima pergunta real do funil (ano).
    st = _troca_state(modelo="Gol", km=280000)  # ano vazio
    out = _run(TurnReply(bubbles=[
        Bubble(text="Boa, esse modelo é bem comum na troca aqui."),
        Bubble(text="Ele tá com quantos km mais ou menos?"),
    ]), st)
    textos = " ".join(b.text.lower() for b in out.bubbles)
    assert "km" not in textos          # não pergunta km de novo
    assert "ano" in textos             # virou a próxima do funil


def test_contexto_menciona_campo_mas_pergunta_e_outra():
    # "esse modelo é comum" no contexto (modelo já preenchido) NÃO deve trocar
    # a pergunta legítima de ano.
    st = _troca_state(modelo="Gol")  # ano vazio
    out = _run(TurnReply(bubbles=[
        Bubble(text="Boa, esse modelo é bem comum na troca aqui."),
        Bubble(text="E o ano dele?"),
    ]), st)
    textos = [b.text for b in out.bubbles]
    assert any("ano" in t.lower() for t in textos)
    assert any("modelo" in t.lower() for t in textos)  # contexto preservado


def test_nao_repergunta_cidade_ja_preenchida():
    st = ensure_keys({})
    st["lead"]["nome"] = "Raul"; st["lead"]["cidade"] = "Joinville"
    st["intencao"] = "troca"
    out = _run(TurnReply(bubbles=[Bubble(text="De qual cidade você é?")]), st)
    assert not any("cidade" in b.text.lower() for b in out.bubbles)


def test_transicao_contextual_com_pergunta_sobrevive():
    st = ensure_keys({}); st["intencao"] = "troca"
    out = _run(TurnReply(bubbles=[
        Bubble(text="Show, atendemos bastante a região. De qual cidade você é?"),
    ]), st)
    assert "atendemos" in out.bubbles[0].text.lower()
    assert out.bubbles[0].text.endswith("?")


# --------------------------------------------------------------------------
# Saudação enviada pelo agente
# --------------------------------------------------------------------------
def test_greeting_texto_exato():
    from app.amanda.greeting import GREETING_TEXT
    assert GREETING_TEXT == (
        "Olá! 😊 Meu nome é Amanda e falo aqui da AutoVip. Tudo bem com você? "
        "Para começarmos, pode me dizer seu nome e de qual cidade está falando?"
    )


def test_has_real_outbound_ignora_activity_e_opportunity():
    from app.amanda.runtime import _has_real_outbound_text
    msgs = [
        {"direction": "outbound", "body": "Opportunity created"},
        {"direction": "outbound", "type": 26, "body": "Appointment"},
    ]
    assert _has_real_outbound_text(msgs) is False


def test_has_real_outbound_detecta_texto_da_loja():
    from app.amanda.runtime import _has_real_outbound_text
    msgs = [{"direction": "outbound", "body": "Olá! Meu nome é Amanda"}]
    assert _has_real_outbound_text(msgs) is True


def test_has_real_outbound_ignora_inbound():
    from app.amanda.runtime import _has_real_outbound_text
    msgs = [{"direction": "inbound", "body": "oi quero um carro"}]
    assert _has_real_outbound_text(msgs) is False


# --------------------------------------------------------------------------
# Nota de escalonamento: uma só + rótulo "Escalonamento"
# --------------------------------------------------------------------------
def test_resumo_usa_escalonamento_nao_handoff():
    from app.agent.state import SessionState, Collected
    from app.orchestrator.dispatch import format_handoff_summary
    txt = format_handoff_summary(SessionState(collected=Collected(nome="Raul")),
                                 "coleta_completa")
    assert "Motivo do escalonamento:" in txt
    assert "handoff" not in txt.lower()


def test_execute_handoff_gera_uma_nota_so():
    # Garante que execute_handoff chama add_note UMA vez (via add_handoff_note),
    # não duas (bug das notas duplicadas).
    import asyncio
    from unittest.mock import AsyncMock, patch
    from app.agent.state import SessionState, Collected
    from app.orchestrator import dispatch
    with patch.object(dispatch.contacts, "add_note", new=AsyncMock(return_value={})) as m_note, \
         patch.object(dispatch.contacts, "update_custom_fields", new=AsyncMock(return_value={})), \
         patch.object(dispatch.contacts, "remove_tag", new=AsyncMock(return_value={})):
        asyncio.run(dispatch.execute_handoff(
            "C1", SessionState(collected=Collected(nome="Raul")), "coleta_completa"))
        assert m_note.await_count == 1


# --------------------------------------------------------------------------
# FAQ vende_carta (vender != aceitar)
# --------------------------------------------------------------------------
def test_faq_tem_vende_carta():
    from app.amanda.tools import _load_local_faq
    faq = _load_local_faq()
    assert "vende_carta" in faq
    txt = faq["vende_carta"].lower()
    assert "não vende" in txt or "nao vende" in txt
    assert "contemplada" in txt


def test_instrucoes_citam_vende_carta():
    assert "vende_carta" in INSTRUCTIONS


# --------------------------------------------------------------------------
# Plano do lead: troca + resto com carta (intent = troca, sem financiamento)
# --------------------------------------------------------------------------
def test_forma_carta_nao_puxa_financiamento():
    st = _troca_state(
        modelo="Gol", ano=2015, km=90000,
        quitado_ou_financiado="quitado", fotos_solicitadas=True,
        forma_pagamento_diferenca="carta",
    )
    funil = funnel_for(st)
    assert "financiamento.cpf" not in funil
    assert missing_fields(st) == []  # coleta completa, sem CPF


def test_intent_troca_aceito_em_frase_plano():
    from app.amanda.tools import _intent_supported_by_msg
    msg = "me chamo raul, sou de joinville, vocês aceitam carro na troca e o resto com carta contemplada?"
    assert _intent_supported_by_msg("troca", msg) is True


# --------------------------------------------------------------------------
# Contexto-fantasma: não comentar modelo antes do lead dizer
# --------------------------------------------------------------------------
def test_contexto_fantasma_removido_sem_modelo():
    # lead só disse "quero trocar"; modelo desconhecido → "esse modelo é comum"
    # é alucinação, deve sair; a pergunta fica.
    st = ensure_keys({}); st["intencao"] = "troca"
    out = _run(TurnReply(bubbles=[
        Bubble(text="Boa, esse modelo é bem comum na troca aqui. Qual o modelo do seu atual?"),
    ]), st)
    txt = " ".join(b.text.lower() for b in out.bubbles)
    assert "esse modelo é bem comum" not in txt
    assert "modelo" in txt  # a pergunta "qual o modelo" permanece


def test_contexto_modelo_mantido_quando_conhecido():
    st = _troca_state(modelo="Gol")
    out = _run(TurnReply(bubbles=[
        Bubble(text="Boa, esse modelo sai bastante."),
        Bubble(text="E o ano dele?"),
    ]), st)
    assert any("sai bastante" in b.text.lower() for b in out.bubbles)


def test_instrucoes_nome_coincide_consultor():
    # regra: nome do lead pode ser "Ramon" (coincide com consultor)
    low = INSTRUCTIONS.lower()
    assert "coincidir com o do consultor" in low or "coincide com o do consultor" in low
