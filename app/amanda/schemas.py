"""Output schemas para o Agent."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Bubble(BaseModel):
    text: str = Field(..., min_length=1, max_length=400)


class TurnReply(BaseModel):
    """Resposta de UM turno da Amanda no WhatsApp.

    Regras (limite EFETIVO = 3 bolhas):
    - 1 a 3 bolhas, curtas, sem markdown, sem numeração.
    - Apenas a ÚLTIMA bolha pode conter uma pergunta (terminar com "?").
    - Em handoff: 1 bolha só, sem pergunta.

    Nota: o schema tolera até 4 bolhas (`max_length=4`) de propósito — se o
    modelo emitir 4, a validação Pydantic não falha (evita cair no fallback
    de string). O contrato real de 3 é imposto pelo post-hook
    `enforce_bubbles`, que é a fonte de verdade única do limite.
    """
    # max_length=4 é margem de tolerância; enforce_bubbles corta para 3.
    bubbles: list[Bubble] = Field(..., min_length=1, max_length=4)
