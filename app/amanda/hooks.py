"""Pre/post/tool hooks da Amanda."""
from __future__ import annotations

import re
import time
from typing import Any

from agno.run.base import RunContext
from loguru import logger

from app import metrics

from app.amanda.state_schema import get_dotted
from app.amanda.tools import _norm

# Aberturas típicas de eco/ack ("Entendi o ...", "Vi o ...", "Recebi ...").
_ECHO_OPENER = re.compile(
    r"^(entendi|show|beleza|perfeito|anotado|anotei|valeu|massa|boa|legal|certo"
    r"|[oó]timo|vi |recebi|peguei|confirmei|obrigad|certo)\b",
    re.IGNORECASE,
)
# Padrões de RE-DECLARAÇÃO de dado (papagaio) em qualquer posição da frase,
# texto já normalizado (minúsculo, sem acento).
_RESTATE = re.compile(
    r"\b(voce (esta|ta) (buscando|querendo|procurando|interessad)"
    r"|voce quer (um|uma)|voce procura|voce (e|eh) de |voce (e|eh) (do|da) "
    r"|seu nome (e|eh) |voce se chama|voce tem (um|uma)|entao (voce|e|eh) "
    r"|vi (o |a |que |seu |sua )|recebi (o |a |seu |sua )"
    r"|que (voce |vai )(vai |enviar|mandar|passar))"
)
# Palavras-de-campo: se uma frase de ack/eco menciona um desses, é papagaio
# (devolvendo dado coletado), mesmo sem dígito.
_FIELD_WORDS = (
    "cpf", "cnh", "rg", "entrada", "parcela", "km", "quilometragem", "ano",
    "nascimento", "nome", "cidade", "modelo", "foto", "fotos", "quitado",
    "financiado",
)


def _split_sentences(text: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p]


def _collected_values(state: dict) -> list[str]:
    """Valores de texto já coletados que NÃO podem ser ecoados de volta."""
    vals: list[str] = []
    for dotted in ("lead.nome", "lead.cidade", "veiculo_interesse", "troca.modelo"):
        v = get_dotted(state, dotted)
        if isinstance(v, str) and len(v.strip()) >= 3:
            vals.append(_norm(v))
    return vals


def _is_echo_sentence(sent: str, vals: list[str]) -> bool:
    """True se a frase é papagaio: 'anotado', ECO LITERAL de um valor coletado
    (devolve o modelo/cidade/nome ou um número que o lead deu), ou re-declaração
    ('você está buscando um X', 'você é de Y'). Pergunta nunca é eco.

    IMPORTANTE (tom natural): reconhecimento COM contexto genérico NÃO é eco —
    "boa, esse modelo é comum na troca" é permitido. Só barramos quando a frase
    DEVOLVE o VALOR literal (texto coletado ou dígito), não a palavra-campo."""
    s = sent.strip()
    n = _norm(s)
    if "anotad" in n or "anotei" in n:
        return True
    if s.endswith("?"):
        return False
    # Eco literal = repete um VALOR de texto coletado (nome/cidade/modelo/veic)
    # ou um número que o lead informou. NÃO usa palavra-campo genérica (senão
    # mata "esse modelo é comum", que é comentário contextual, não eco).
    has_literal_value = any(c.isdigit() for c in s) or any(v in n for v in vals)
    if _ECHO_OPENER.match(s) and has_literal_value:
        return True
    if _RESTATE.search(n):
        return True
    return False


def _strip_echo(bubbles: list, state: dict) -> tuple[list, bool]:
    """Remove frases-papagaio de QUALQUER posição. Mantém o resto (perguntas,
    FAQ, deflexão). Nunca esvazia toda a resposta."""
    vals = _collected_values(state)
    new: list = []
    changed = False
    for b in bubbles:
        sents = _split_sentences(b.text)
        kept = [s for s in sents if not _is_echo_sentence(s, vals)]
        if len(kept) != len(sents):
            changed = True
            rest = " ".join(kept).strip()
            if rest:
                b.text = rest
                new.append(b)
            # bolha era só eco → descartada
        else:
            new.append(b)
    if not new:  # segurança: nunca devolve resposta vazia
        return bubbles, False
    return new, changed


def _collapse_questions(bubbles: list) -> tuple[list, bool]:
    """Garante NO MÁXIMO 1 pergunta por turno (a última). Bolhas-pergunta
    anteriores (duplicadas) são descartadas."""
    q_idx = [i for i, b in enumerate(bubbles) if "?" in b.text]
    if len(q_idx) <= 1:
        return bubbles, False
    keep = q_idx[-1]
    new = [b for i, b in enumerate(bubbles) if i == keep or "?" not in b.text]
    return new, True


# Meta-perguntas / ofertas de explicar (proibidas — a pergunta deve ser de
# qualificação ou oferta de visita).
_META_Q = re.compile(
    r"(quer que eu (te )?(explique|detalhe|fale|conte|mostre|ajude)"
    r"|quer saber (sobre|mais)|posso (te )?ajudar (com|em) (mais )?alguma"
    r"|tem (mais )?(alguma )?(d[uú]vida|pergunta)|quer mais (detalhe|informa)"
    r"|gostaria de saber mais|precisa de mais (alguma )?(coisa|informa))"
)

# Perguntas FORA DO ROTEIRO (puxar-papo) que o modelo às vezes cria no tom
# consultivo. Não são campos do funil → trocamos pela pergunta do funil.
_OFFSCRIPT_Q = re.compile(
    r"(ha quanto tempo|faz (quanto )?tempo que (tem|voce tem|e seu)"
    r"|por que (voce )?(quer|decidiu|pensa em) troc|o que (te )?(fez|levou|motiv)"
    r"|ja pensou em algum (modelo|carro)|qual (cor|a cor)"
    r"|usa (muito|bastante) o carro|e pra voce ou pra (familia|alguem)"
    r"|pra que (voce )?(usa|vai usar))"
)


def _fix_meta_question(bubbles: list, state: dict) -> tuple[list, bool]:
    """Se a última bolha for meta-pergunta (oferta de explicar) OU pergunta
    fora do roteiro (puxar-papo), troca pela próxima pergunta de qualificação
    do funil. Se não houver pergunta pendente, remove o '?' (vira afirmação)."""
    if not bubbles:
        return bubbles, False
    last = bubbles[-1]
    nlast = _norm(last.text)
    if "?" not in last.text or not (_META_Q.search(nlast) or _OFFSCRIPT_Q.search(nlast)):
        return bubbles, False
    from app.amanda.state_schema import ensure_keys
    from app.amanda.tools import pick_next_question

    try:
        _, _, sugestao = pick_next_question(ensure_keys(state))
    except Exception:
        sugestao = None
    if sugestao:
        last.text = sugestao
    else:
        last.text = last.text.replace("?", ".")
    return bubbles, True


# Pergunta que pede um campo JÁ preenchido (o lead informou vários dados numa
# msg só, o modelo gravou tudo mas ainda perguntou um deles). Roda no post-hook
# com o state PÓS-registro → troca pela próxima pergunta REAL do funil.
_FIELD_Q_KEYWORDS = (
    ("financiamento.cpf", re.compile(r"\bcpf\b")),
    ("financiamento.parcela_desejada", re.compile(r"\bparcela\b")),
    ("financiamento.entrada", re.compile(r"\bentrada\b")),
    ("financiamento.data_nascimento", re.compile(r"nascimento|data de nasc")),
    ("troca.km", re.compile(r"\b(km|quilomet)")),
    ("troca.ano", re.compile(r"\bano\b")),
    ("troca.modelo", re.compile(r"\bmodelo\b")),
    ("lead.cidade", re.compile(r"\bcidade\b|de onde (voce )?(e|fala|vem)")),
    ("lead.nome", re.compile(r"como (posso )?(te|lhe) chamar|seu nome|qual seu nome")),
)


def _fix_asks_filled_field(bubbles: list, state: dict) -> tuple[list, bool]:
    from app.amanda.state_schema import ensure_keys, get_dotted
    from app.amanda.tools import pick_next_question

    if not bubbles:
        return bubbles, False
    last = bubbles[-1]
    if "?" not in last.text:
        return bubbles, False
    # Só olha a(s) frase(s) INTERROGATIVA(s) — evita casar palavra-campo que
    # aparece só no micro-contexto ("esse modelo é comum. E o ano?").
    q_sentences = [s for s in _split_sentences(last.text) if s.strip().endswith("?")]
    n = _norm(" ".join(q_sentences))
    if not n:
        return bubbles, False
    st = ensure_keys(state)
    for field, pat in _FIELD_Q_KEYWORDS:
        val = get_dotted(st, field)
        if val not in (None, "") and pat.search(n):
            # a pergunta pede um campo já coletado → troca pela próxima do funil
            try:
                _, _, sugestao = pick_next_question(st)
            except Exception:
                sugestao = None
            if sugestao and _norm(sugestao) != n:
                last.text = sugestao
                return bubbles, True
            # sem próxima pergunta (funil completo) → vira afirmação neutra
            last.text = "Perfeito, vamos seguir."
            return bubbles, True
    return bubbles, False


# Muletas/preâmbulos vazios no INÍCIO da frase ("Agora me diz", "Me conta",
# "Pra continuar, me diz"...). Removidos — pergunta vai direto. NÃO casa
# justificativas específicas ("Pra adiantar a simulação, ...").
_TIC_PREFIX = re.compile(
    r"^\s*"
    r"(?:(?:agora|ent[aã]o|bom|olha|veja|beleza|certo)[,!.:]?\s+)?"
    r"(?:(?:me\s+(?:diz|conta|fala)|diz\s+a[ií]|"
    r"pra\s+(?:continuar|seguir|avan[cç]ar|gente\s+(?:continuar|seguir|avan[cç]ar)))"
    r"[,!.:]?\s+)+",
    re.IGNORECASE,
)


def _strip_tics(text: str) -> str:
    new = _TIC_PREFIX.sub("", text).lstrip(" ,:-")
    if not new or new == text:
        return text
    return new[0].upper() + new[1:]


def _ensure_funnel_question(bubbles: list, state: dict) -> tuple[list, bool]:
    """Garante que todo turno de qualificação ATIVA termine com uma pergunta
    do funil. Se o funil está incompleto, não houve handoff, e nenhuma bolha
    tem pergunta → adiciona a próxima pergunta canônica. Assim o agente nunca
    "responde e para" sem avançar a qualificação."""
    from app.amanda.schemas import Bubble
    from app.amanda.state_schema import ensure_keys, missing_fields
    from app.amanda.tools import pick_next_question

    st = ensure_keys(state)
    if (st.get("handoff") or {}).get("feito"):
        return bubbles, False
    if not missing_fields(st):
        return bubbles, False  # funil completo → oferta de visita/handoff cuida
    # "Já tem pergunta" = tem "?" OU já contém um pedido de campo canônico sem
    # "?" (ex.: a frase de CPF termina em "por gentileza", sem interrogação).
    if any("?" in b.text for b in bubbles) or any(_CPF_ASK.search(b.text) for b in bubbles):
        return bubbles, False
    _, _, sugestao = pick_next_question(st)
    if not sugestao:
        return bubbles, False
    bubbles = list(bubbles) + [Bubble(text=sugestao)]
    if len(bubbles) > 3:  # respeita o limite, mantém a pergunta no fim
        bubbles = bubbles[:2] + [bubbles[-1]]
    return bubbles, True


# Léxico proibido: a Auto Vip nunca chama o produto de "carrinho" — sempre
# "carro"/"veículo". Rede de segurança determinística caso o modelo escorregue.
_CARRINHO = re.compile(r"\bcarrinho(s)?\b", re.IGNORECASE)


def _match_case(replacement: str, original: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _fix_lexicon(bubbles: list) -> tuple[list, bool]:
    """Troca 'carrinho'→'carro' (e 'carrinhos'→'carros') em toda bolha."""
    changed = False
    for b in bubbles:
        def _sub(m: "re.Match") -> str:
            word = m.group(0)
            plural = bool(m.group(1))
            return _match_case("carros" if plural else "carro", word)

        new_text = _CARRINHO.sub(_sub, b.text)
        if new_text != b.text:
            changed = True
            b.text = new_text
    return bubbles, changed


# Pedido de CPF: frase canônica obrigatória. O modelo às vezes gera uma
# paráfrase curta E a canônica (2 bolhas), ou só parafraseia. Este guard força
# UMA única bolha de CPF, exatamente a frase canônica.
_CPF_ASK = re.compile(r"\bcpf\b", re.IGNORECASE)


def _canonicalize_cpf_ask(bubbles: list) -> tuple[list, bool]:
    from app.amanda.tools import _SUGESTOES
    canonical = _SUGESTOES["financiamento.cpf"]
    out: list = []
    seen = False
    changed = False
    for b in bubbles:
        if _CPF_ASK.search(b.text):
            if seen:
                changed = True  # descarta bolha de CPF redundante
                continue
            seen = True
            if b.text.strip() != canonical:
                b.text = canonical
                changed = True
        out.append(b)
    return out, changed


# Deflexão indevida: quando a Amanda ACABOU de perguntar um valor de funil
# (parcela/entrada) e o lead RESPONDEU com o valor, o modelo às vezes trata a
# resposta como "pergunta de preço" e deflita ("quem confirma é o consultor").
# Isso é errado — o lead só respondeu. Deflexão sobre esse valor só cabe se o
# lead PERGUNTAR o valor (msg com "?").
_DEFLEXAO_SIG = re.compile(
    r"(quem confirma|o consultor|pro consultor|"
    r"consultor (te|confirma|passa|detalha|ver|responder)|deixa (eu )?adiantar)"
)
_VALUE_ASK_FIELDS = {
    "financiamento.parcela_desejada": ("parcela",),
    "financiamento.entrada": ("entrada",),
}


def _strip_wrong_deflexao(bubbles: list, state: dict) -> tuple[list, bool]:
    la = state.get("last_asked") or []
    if not la:
        return bubbles, False
    topics = _VALUE_ASK_FIELDS.get(la[-1])
    if not topics:
        return bubbles, False
    msg = _norm(state.get("_last_user_msg") or "")
    if not msg or "?" in msg:
        return bubbles, False  # lead PERGUNTOU o valor → deflexão é legítima
    new: list = []
    changed = False
    for b in bubbles:
        n = _norm(b.text)
        if _DEFLEXAO_SIG.search(n) and any(t in n for t in topics):
            changed = True
            continue  # descarta deflexão indevida sobre o valor que o lead deu
        new.append(b)
    if not new:
        return bubbles, False  # nunca esvazia a resposta
    return new, changed


def _dedup_bubbles(bubbles: list) -> tuple[list, bool]:
    """Remove bolhas com texto idêntico/quase-idêntico (normalizado),
    mantendo a primeira ocorrência."""
    seen: set[str] = set()
    new: list = []
    changed = False
    for b in bubbles:
        key = _norm(b.text)
        if key in seen:
            changed = True
            continue
        seen.add(key)
        new.append(b)
    return new, changed


def log_tool_call(function_name: str, func, args: dict[str, Any]):
    """Tool middleware — loga cada chamada com latência."""
    t0 = time.perf_counter()
    metrics.TOOL_CALLS.labels(name=function_name).inc()
    try:
        result = func(**args)
        dt_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "tool.call name={} latency_ms={} args_keys={}",
            function_name, dt_ms, list(args.keys()),
        )
        return result
    except Exception as e:
        dt_ms = int((time.perf_counter() - t0) * 1000)
        logger.exception(
            "tool.error name={} latency_ms={} err={}",
            function_name, dt_ms, e,
        )
        raise


def _run_pipeline(bubbles: list, state: dict) -> list:
    """Pipeline ÚNICO de enforcement das bolhas — usado tanto pelo caminho
    normal quanto pelo recovery de string. Trim → anti-eco → colapsa pergunta
    dupla → dedup → meta → funnel → tics → ?-só-na-última."""
    if len(bubbles) > 3:
        metrics.BUBBLE_VIOLATIONS.labels(kind="too_many").inc()
        bubbles = bubbles[:3]

    bubbles, echoed = _strip_echo(bubbles, state)
    if echoed:
        metrics.BUBBLE_VIOLATIONS.labels(kind="echo").inc()

    bubbles, collapsed = _collapse_questions(bubbles)
    if collapsed:
        metrics.BUBBLE_VIOLATIONS.labels(kind="duplicate_question").inc()

    bubbles, deduped = _dedup_bubbles(bubbles)
    if deduped:
        metrics.BUBBLE_VIOLATIONS.labels(kind="duplicate_bubble").inc()

    bubbles, lexfixed = _fix_lexicon(bubbles)
    if lexfixed:
        metrics.BUBBLE_VIOLATIONS.labels(kind="lexicon_carrinho").inc()

    bubbles, cpffixed = _canonicalize_cpf_ask(bubbles)
    if cpffixed:
        metrics.BUBBLE_VIOLATIONS.labels(kind="cpf_ask_canonicalized").inc()

    bubbles, defstripped = _strip_wrong_deflexao(bubbles, state)
    if defstripped:
        metrics.BUBBLE_VIOLATIONS.labels(kind="wrong_deflexao").inc()

    bubbles, metafixed = _fix_meta_question(bubbles, state)
    if metafixed:
        metrics.BUBBLE_VIOLATIONS.labels(kind="meta_question").inc()

    bubbles, filledfix = _fix_asks_filled_field(bubbles, state)
    if filledfix:
        metrics.BUBBLE_VIOLATIONS.labels(kind="asks_filled_field").inc()

    bubbles, added_q = _ensure_funnel_question(bubbles, state)
    if added_q:
        metrics.BUBBLE_VIOLATIONS.labels(kind="missing_funnel_question").inc()

    for b in bubbles:
        stripped = _strip_tics(b.text)
        if stripped != b.text:
            metrics.BUBBLE_VIOLATIONS.labels(kind="tic_stripped").inc()
            b.text = stripped

    for b in bubbles[:-1]:
        if "?" in b.text:
            metrics.BUBBLE_VIOLATIONS.labels(kind="question_not_last").inc()
            b.text = b.text.replace("?", ".")
    return bubbles


def _recover_bubbles_from_string(content: str):
    """Reconstrói bolhas de uma string com JSON(s) concatenado(s)
    {"bubbles":[...]}{"bubbles":[...]}. Retorna lista de textos (ou [])."""
    import json
    decoder = json.JSONDecoder()
    i = 0
    collected: list[str] = []
    s = content.strip()
    while i < len(s):
        try:
            obj, end = decoder.raw_decode(s, i)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict) and "bubbles" in obj:
            for b in obj["bubbles"]:
                if isinstance(b, dict) and "text" in b:
                    collected.append(str(b["text"])[:400])
        i = end
        while i < len(s) and s[i] in " \n\t":
            i += 1
    return collected


def enforce_bubbles(run_context: RunContext, run_output) -> None:
    """Post-hook: valida bolhas. Caminho normal E recovery de string passam
    pelo MESMO pipeline (`_run_pipeline`) — sem atalho que pule as defesas."""
    from app.amanda.schemas import Bubble, TurnReply
    try:
        content = run_output.content
        state = getattr(run_context, "session_state", None) or {}

        if isinstance(content, str):
            logger.warning("post_hook.string_content fallback len={}", len(content))
            metrics.BUBBLE_VIOLATIONS.labels(kind="string_fallback").inc()
            collected = _recover_bubbles_from_string(content)
            if collected:
                bubbles = [Bubble(text=t) for t in collected]
                metrics.BUBBLE_VIOLATIONS.labels(kind="recovered").inc()
            else:
                txt = content.strip()[:400] or "Deixa eu organizar aqui e já volto."
                bubbles = [Bubble(text=txt)]
            bubbles = _run_pipeline(bubbles, state)
            if bubbles:
                run_output.content = TurnReply(bubbles=bubbles)
            return

        if content is None or not hasattr(content, "bubbles") or not content.bubbles:
            return
        bubbles = _run_pipeline(content.bubbles, state)
        if bubbles:
            content.bubbles = bubbles
    except Exception as e:
        logger.exception("post_hook.enforce_bubbles err={}", e)
