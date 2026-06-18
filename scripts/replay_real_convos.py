"""Replay das 3 conversas reais contra o novo agente, modo offline (SqliteDb).

Para cada conversa, replica as mensagens inbound do lead em ordem e mostra
o que a Amanda Agno responderia.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, ".")

# carrega .env manualmente
for line in Path(".env").read_text().splitlines():
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from agno.agent import Agent  # noqa: E402
from agno.db.sqlite import SqliteDb  # noqa: E402
from agno.models.openai import OpenAIChat  # noqa: E402

from app.amanda.hooks import enforce_bubbles, log_tool_call  # noqa: E402
from app.amanda.instructions import INSTRUCTIONS  # noqa: E402
from app.amanda.schemas import TurnReply  # noqa: E402
from app.amanda.tools import ALL_TOOLS  # noqa: E402


CONVERSAS = {
    "fhFns2iHTh8VVUFMSI77 — Maicon (Toyota Corolla / Onix)": [
        "Oi",
        "Tem ainda o Corolla 2011/2012?",
        "Pega outro carro no negócio?",
        "Maicon",
        "Itajai",
        "Não entendi a pergunta?",
        "Meu carro é um Onix",
        "2018",
        "Não sei agora. Ele tá na garagem",
        "Não sei te dizer",
        "Financiado",
        "80 mil",
    ],
    "4XChoktzKo2znh4KgzAJ — Ramon (Saveiro)": [
        "Qual o valor da Saveiro?",
        "Pega carro na troca?",
        "Pega carro no negócio?",
        "Vou perguntar mais uma vez. Pega carro no negócio?",
        "Não quero mais falar com você",
        "Tchau",
    ],
    "51mMdj436E9w93NvM5dZ — Raul (Joinville)": [
        "Raul",
        "To procurando um carro pra minha esposa",
        "Sou de Joinville",
        "10349706905",
    ],
}


async def replay(sid: str, agent: Agent, msgs: list[str]) -> None:
    print("\n" + "=" * 80)
    print(f"## {sid}")
    print("=" * 80)
    for i, m in enumerate(msgs, 1):
        print(f"\n[{i}] **Lead**: {m}")
        try:
            out = await agent.arun(input=m, session_id=sid, user_id=sid)
        except Exception as e:
            print(f"  !! erro: {e}")
            continue
        if hasattr(out.content, "bubbles"):
            for b in out.content.bubbles:
                print(f"     **Amanda**: {b.text}")
        else:
            print(f"     !! sem bubbles: {str(out.content)[:200]}")
    st = await agent.aget_session_state(session_id=sid)
    print("\n--- ESTADO FINAL ---")
    print(f"lead: {st.get('lead')}")
    print(f"intencao: {st.get('intencao')}")
    print(f"troca: {st.get('troca')}")
    print(f"financiamento: {st.get('financiamento')}")
    print(f"pendencias: {st.get('pendencias')}")
    print(f"handoff: {st.get('handoff')}")


async def main() -> None:
    db_path = "/tmp/amanda_replay.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    db = SqliteDb(db_file=db_path)
    agent = Agent(
        name="Amanda",
        model=OpenAIChat(id="gpt-4.1-mini", temperature=0.6),
        db=db,
        instructions=INSTRUCTIONS,
        tools=ALL_TOOLS,
        output_schema=TurnReply,
        add_history_to_context=True,
        num_history_runs=8,
        add_session_state_to_context=True,
        enable_agentic_state=True,
        add_datetime_to_context=True,
        tool_call_limit=10,
        tool_hooks=[log_tool_call],
        post_hooks=[enforce_bubbles],
    )
    for sid, msgs in CONVERSAS.items():
        await replay(sid, agent, msgs)


if __name__ == "__main__":
    asyncio.run(main())
