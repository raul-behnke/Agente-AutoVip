"""Saudação inicial enviada pelo PRÓPRIO agente (não mais pelo GHL).

Disparada no primeiro toque do webhook para um contato ainda não saudado
(`greeted=False`), antes de qualquer mensagem do lead. Idempotente: o flag
`greeted` no session_state garante que só sai UMA vez por conversa.
"""
from __future__ import annotations

GREETING_TEXT = (
    "Olá! 😊 Meu nome é Amanda e falo aqui da AutoVip. Tudo bem com você? "
    "Para começarmos, pode me dizer seu nome e de qual cidade está falando?"
)
