"""Offline tests for the Agno-native Amanda runtime.

These scenarios are based on `conversas.md` and avoid real OpenAI/GHL calls by
stubbing the agent, database, conversation API, and sender.
"""
from __future__ import annotations

import asyncio
import copy
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.amanda import runtime  # noqa: E402
from app.amanda.agent import get_agent  # noqa: E402
from app.amanda.schemas import Bubble, TurnReply  # noqa: E402
from app.amanda.state_schema import default_state  # noqa: E402
from app.ghl import conversations  # noqa: E402
from app.orchestrator import concat, sender  # noqa: E402


class FakeDb:
    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state

    def get_session(self, session_id: str, session_type: Any = None) -> Any | None:
        if self.state is None:
            return None
        return SimpleNamespace(session_data={"session_state": copy.deepcopy(self.state)})


class FakeAgent:
    def __init__(
        self,
        state: dict[str, Any] | None = None,
        bubbles: list[str] | None = None,
        delay: float = 0.0,
    ) -> None:
        self.db = FakeDb(state)
        self.bubbles = bubbles or ["Resposta teste"]
        self.delay = delay
        self.run_calls: list[dict[str, Any]] = []
        self.session_state_after_run: dict[str, Any] | None = None

    async def arun(
        self,
        input: str,
        session_id: str,
        user_id: str,
        session_state: dict[str, Any],
    ) -> Any:
        self.run_calls.append(
            {
                "input": input,
                "session_id": session_id,
                "user_id": user_id,
                "session_state": copy.deepcopy(session_state),
                "at": time.monotonic(),
            }
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        self.session_state_after_run = copy.deepcopy(session_state)
        return SimpleNamespace(
            content=TurnReply(bubbles=[Bubble(text=b) for b in self.bubbles])
        )

    async def aget_session_state(self, session_id: str) -> dict[str, Any] | None:
        return copy.deepcopy(self.session_state_after_run)


def _reset_runtime() -> None:
    runtime.active_tasks.clear()
    runtime.sending_flags.clear()
    runtime.pending_reprocess.clear()


def _install_common_stubs(
    *,
    messages: list[dict],
    agent: FakeAgent,
    send_calls: list[tuple[str, str, float]],
) -> None:
    async def fake_search(contact_id: str) -> str:
        return "conv-maicon"

    async def fake_get_messages(conversation_id: str, limit: int = 50) -> list[dict]:
        return copy.deepcopy(messages)

    async def fake_send_blocks(contact_id: str, blocks: list[str], delay_ms: int | None = None) -> None:
        for block in blocks:
            send_calls.append((contact_id, block, time.monotonic()))

    async def fake_execute_handoff(contact_id: str, state: Any, reason: str) -> None:
        raise AssertionError("handoff should not run in this test")

    conversations.search_conversation = fake_search  # type: ignore[assignment]
    conversations.get_messages = fake_get_messages  # type: ignore[assignment]
    sender.send_blocks = fake_send_blocks  # type: ignore[assignment]
    runtime.get_agent = lambda: agent  # type: ignore[assignment]
    runtime.execute_handoff = fake_execute_handoff  # type: ignore[assignment]


def _maicon_messages_tail() -> list[dict]:
    """Fixture derived from the Maicon/Onix tail in conversas.md."""
    return [
        {
            "id": "act-1",
            "type": 25,
            "direction": "outbound",
            "dateAdded": "2026-06-09T20:44:53.178Z",
            "body": "Opportunity updated",
        },
        {
            "id": "a1",
            "direction": "outbound",
            "dateAdded": "2026-06-09T20:45:13.358Z",
            "body": "Como pretende pagar a diferença, à vista ou financiando?",
            "attachments": [],
        },
        {
            "id": "l1",
            "direction": "inbound",
            "dateAdded": "2026-06-09T20:57:15.775Z",
            "body": "https://p.bancopan.com.br/dVbHaZP",
            "attachments": [],
        },
    ]


def _maicon_media_messages() -> list[dict]:
    return [
        {
            "id": "a1",
            "direction": "outbound",
            "dateAdded": "2026-06-09T13:00:11.409Z",
            "body": "Qual a quilometragem aproximada do seu Onix?",
            "attachments": [],
        },
        {
            "id": "i1",
            "direction": "inbound",
            "dateAdded": "2026-06-09T20:44:33.062Z",
            "body": "type message: image\n\nSource: Ramon",
            "attachments": [{"url": "https://cdn.example.com/onix-frente.jpg"}],
        },
        {
            "id": "d1",
            "direction": "inbound",
            "dateAdded": "2026-06-09T20:57:15.775Z",
            "body": "https://p.bancopan.com.br/dVbHaZP",
            "attachments": [],
        },
    ]


async def test_concat_maicon_media_tail() -> None:
    pending = concat.extract_pending_inbounds(_maicon_media_messages())
    ids = [m["id"] for m in pending]
    assert ids == ["i1", "d1"], ids

    turn_input, photo_count = await concat.build_turn_input(pending)
    assert "[Cliente enviou 1 foto(s)]" in turn_input, turn_input
    assert "https://p.bancopan.com.br/dVbHaZP" in turn_input, turn_input
    assert "type message: image" not in turn_input, turn_input
    assert photo_count == 1, photo_count


async def test_concat_preserves_text_sms_with_ghl_source_metadata() -> None:
    messages = [
        {
            "id": "a1",
            "direction": "outbound",
            "dateAdded": "2026-06-10T16:22:45.545Z",
            "body": "Oi! Tudo certo por aí?",
            "attachments": [],
        },
        {
            "id": "l1",
            "direction": "inbound",
            "dateAdded": "2026-06-10T16:23:05.264Z",
            "body": "Sou de Joinville\n\nSource: Ramon",
            "attachments": None,
        },
        {
            "id": "l2",
            "direction": "inbound",
            "dateAdded": "2026-06-10T16:24:04.512Z",
            "body": "Me chamo Raul, vocês aceitam troca?\n\nSource: Ramon",
            "attachments": None,
        },
        {
            "id": "l3",
            "direction": "inbound",
            "dateAdded": "2026-06-10T16:24:09.353Z",
            "body": "Tem algum Corolla\n\nSource: Ramon",
            "attachments": None,
        },
    ]

    pending = concat.extract_pending_inbounds(messages)
    turn_input, photo_count = await concat.build_turn_input(pending)

    assert turn_input == (
        "Sou de Joinville\n"
        "Me chamo Raul, vocês aceitam troca?\n"
        "Tem algum Corolla"
    )
    assert "Source:" not in turn_input
    assert "anexo" not in turn_input.lower()
    assert photo_count == 0


async def test_agent_does_not_enable_broken_builtin_state_tool() -> None:
    agent = get_agent()
    assert agent.enable_agentic_state is False


async def test_process_turn_seeds_ad_meta_and_runs_agno() -> None:
    _reset_runtime()
    send_calls: list[tuple[str, str, float]] = []
    agent = FakeAgent(bubbles=["Tudo certo, Maicon", "Vou seguir por aqui"])
    _install_common_stubs(messages=_maicon_messages_tail(), agent=agent, send_calls=send_calls)

    await runtime.process_turn(
        "fhFns2iHTh8VVUFMSI77",
        ad_meta={"veiculo_interesse": "Toyota Corolla 2011/2012", "ano": "2012"},
    )

    assert len(agent.run_calls) == 1
    call = agent.run_calls[0]
    assert "Histórico recente do WhatsApp:" in call["input"]
    assert "Amanda: Como pretende pagar a diferença" in call["input"]
    assert "Mensagem atual do lead:\nhttps://p.bancopan.com.br/dVbHaZP" in call["input"]
    state = call["session_state"]
    assert state["ad_meta"]["veiculo_interesse"] == "Toyota Corolla 2011/2012"
    assert state["ad_meta"]["ano"] == "2012"
    assert state["veiculo_interesse"] == "Toyota Corolla 2011/2012"
    assert [c[1] for c in send_calls] == ["Tudo certo, Maicon", "Vou seguir por aqui"]


async def test_runtime_passes_clean_ghl_history_to_agno() -> None:
    _reset_runtime()
    send_calls: list[tuple[str, str, float]] = []
    messages = [
        {
            "id": "a1",
            "direction": "outbound",
            "dateAdded": "2026-06-10T16:22:45.545Z",
            "body": "Oi! Tudo certo por aí?\n\nPra te atender melhor, me diz seu nome e sua cidade 😊",
            "attachments": [],
        },
        {
            "id": "l1",
            "direction": "inbound",
            "dateAdded": "2026-06-10T16:23:05.264Z",
            "body": "Sou de Joinville\n\nSource: Ramon",
            "attachments": None,
        },
        {
            "id": "a2",
            "direction": "outbound",
            "dateAdded": "2026-06-10T16:23:41.841Z",
            "body": "Oi! Sou da equipe Auto Vip. Como posso te chamar?",
            "attachments": [],
        },
        {
            "id": "l2",
            "direction": "inbound",
            "dateAdded": "2026-06-10T16:24:04.512Z",
            "body": "Me chamo Raul, vocês aceitam troca?\n\nSource: Ramon",
            "attachments": None,
        },
        {
            "id": "l3",
            "direction": "inbound",
            "dateAdded": "2026-06-10T16:24:09.353Z",
            "body": "Tem algum Corolla\n\nSource: Ramon",
            "attachments": None,
        },
    ]
    agent = FakeAgent(bubbles=["Resposta com contexto"])
    _install_common_stubs(messages=messages, agent=agent, send_calls=send_calls)

    await runtime.process_turn("OQphrmBuisVvyspWiZXC")

    assert len(agent.run_calls) == 1
    agent_input = agent.run_calls[0]["input"]
    assert "Cliente: Sou de Joinville" in agent_input
    assert "Amanda: Oi! Sou da equipe Auto Vip. Como posso te chamar?" in agent_input
    assert "Mensagem atual do lead:" in agent_input
    assert "Me chamo Raul, vocês aceitam troca?" in agent_input
    assert "Tem algum Corolla" in agent_input
    assert "Source:" not in agent_input
    assert "anexo" not in agent_input.lower()


async def test_recent_handoff_is_terminal_and_does_not_reply() -> None:
    _reset_runtime()
    send_calls: list[tuple[str, str, float]] = []
    prev_state = default_state()
    prev_state["handoff"] = {"feito": True, "motivo": "coleta_completa"}
    agent = FakeAgent(state=prev_state)
    recent = datetime.now(timezone.utc) - timedelta(minutes=10)
    messages = [
        {
            "id": "a1",
            "direction": "outbound",
            "dateAdded": recent.isoformat().replace("+00:00", "Z"),
            "body": "Vou te passar para um consultor.",
        },
        {
            "id": "l1",
            "direction": "inbound",
            "dateAdded": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "body": "ok",
        },
    ]
    _install_common_stubs(messages=messages, agent=agent, send_calls=send_calls)

    await runtime.process_turn("fhFns2iHTh8VVUFMSI77")

    assert agent.run_calls == []
    assert send_calls == []


async def test_old_handoff_reopens_and_resets_flags() -> None:
    _reset_runtime()
    send_calls: list[tuple[str, str, float]] = []
    prev_state = default_state()
    prev_state["handoff"] = {"feito": True, "motivo": "coleta_completa"}
    prev_state["agendamento"]["oferecido"] = True
    prev_state["last_asked"] = ["troca.km"]
    agent = FakeAgent(state=prev_state)
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    messages = [
        {
            "id": "a1",
            "direction": "outbound",
            "dateAdded": old.isoformat().replace("+00:00", "Z"),
            "body": "Vou te passar para um consultor.",
        },
        {
            "id": "l1",
            "direction": "inbound",
            "dateAdded": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "body": "Voltei, ainda tenho interesse",
        },
    ]
    _install_common_stubs(messages=messages, agent=agent, send_calls=send_calls)

    await runtime.process_turn("fhFns2iHTh8VVUFMSI77")

    assert len(agent.run_calls) == 1
    state = agent.run_calls[0]["session_state"]
    assert state["handoff"] == {"feito": False, "motivo": None}
    assert state["agendamento"]["oferecido"] is False
    assert state["last_asked"] == []
    assert state["counters"]["reopen"] == 1
    assert send_calls


async def test_cancel_and_reprocess_semantics_with_agno_runtime() -> None:
    _reset_runtime()
    send_calls: list[tuple[str, str, float]] = []
    agent = FakeAgent(bubbles=["A", "B"], delay=0.2)
    _install_common_stubs(messages=_maicon_messages_tail(), agent=agent, send_calls=send_calls)

    await runtime.handle_inbound("fhFns2iHTh8VVUFMSI77")
    await asyncio.sleep(0.03)
    await runtime.handle_inbound("fhFns2iHTh8VVUFMSI77")
    await asyncio.sleep(0.03)
    await runtime.handle_inbound("fhFns2iHTh8VVUFMSI77")

    task = runtime.active_tasks.get("fhFns2iHTh8VVUFMSI77")
    if task:
        await task

    assert len(agent.run_calls) == 3
    assert [c[1] for c in send_calls] == ["A", "B"]


async def main() -> None:
    tests = [
        test_concat_maicon_media_tail,
        test_concat_preserves_text_sms_with_ghl_source_metadata,
        test_agent_does_not_enable_broken_builtin_state_tool,
        test_process_turn_seeds_ad_meta_and_runs_agno,
        test_runtime_passes_clean_ghl_history_to_agno,
        test_recent_handoff_is_terminal_and_does_not_reply,
        test_old_handoff_reopens_and_resets_flags,
        test_cancel_and_reprocess_semantics_with_agno_runtime,
    ]
    failed = False
    for test in tests:
        try:
            await test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed = True
            print(f"FAIL {test.__name__}: {exc}")
            import traceback

            traceback.print_exc()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
