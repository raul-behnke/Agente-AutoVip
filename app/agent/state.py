"""Schemas Pydantic para session_state e StateUpdate."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "coleta",
    "duvida",
    "pedido_humano",
    "irritacao",
    "agendamento",
    "apresentacao",
    "outro",
]
IntentSecundario = Literal["duvida_operacional", "pedido_foto", "none"]
Sentiment = Literal["neutro", "positivo", "negativo", "irritado"]
Stage = Literal["abertura", "coleta", "fechamento", "fechado"]
Intencao = Literal["troca", "financiamento", "vista", "carta_credito", "primeiro_carro"]
Regiao = Literal["local", "longe"]
QuitadoOuFinanciado = Literal["quitado", "financiado"]
FormaPagamentoDiferenca = Literal["vista", "financiamento"]
HandoffReason = Literal[
    "irritacao",
    "pedido_humano",
    "fora_escopo",
    "coleta_completa",
    "agendamento_confirmado",
    "simulacao_solicitada",
    "lead_nao_respondeu",
    "none",
]


class TrocaInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    modelo: str | None = None
    ano: int | None = None
    km: int | None = None
    quitado_ou_financiado: QuitadoOuFinanciado | None = None
    fotos_solicitadas: bool | None = None
    forma_pagamento_diferenca: FormaPagamentoDiferenca | None = None


class FinanciamentoInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cpf: str | None = None
    data_nascimento: str | None = None
    entrada: str | None = None
    parcela_desejada: str | None = None
    cnh: bool | None = None


class Collected(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nome: str | None = None
    cidade: str | None = None
    veiculo_interesse: str | None = None
    intencao: Intencao | None = None
    troca: TrocaInfo | None = None
    financiamento: FinanciamentoInfo | None = None
    vista_confirmado: bool | None = None
    carta_credito_contemplada: bool | None = None


class Agendamento(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tipo: Literal["presencial", "video"] | None = None
    data_hora: str | None = None
    appointment_id: str | None = None


class SessionState(BaseModel):
    """Shape persistido como JSONB."""
    model_config = ConfigDict(extra="ignore")

    stage: Stage = "abertura"
    greeted: bool = False
    collected: Collected = Field(default_factory=Collected)
    agendamento: Agendamento | None = None
    pendencias: list[str] = Field(default_factory=list)
    last_asked_fields: list[str] = Field(default_factory=list)
    humano_solicitado_count: int = 0
    ai_identity_asked_count: int = 0
    last_sentiment: Sentiment = "neutro"
    last_intent: Intent = "coleta"
    terminal_reason: HandoffReason | None = None
    handed_off: bool = False
    regiao: Regiao | None = None
    agendamento_oferecido: bool = False
    reopen_count: int = 0


# ---- Updater output -------------------------------------------------------

class StateUpdate(BaseModel):
    """Output estruturado do updater LLM. Só extração, sem geração de texto."""
    model_config = ConfigDict(extra="ignore")

    collected: Collected
    agendamento: Agendamento | None = Field(
        default=None,
        description="Inferência opcional de agendamento (tipo presencial/video, data_hora ISO).",
    )
    intent: Intent
    intent_secundario: IntentSecundario = "none"
    sentiment: Sentiment = "neutro"
    should_handoff: bool = False
    handoff_reason: HandoffReason = "none"
    pendencias_novas: list[str] = Field(
        default_factory=list,
        description="Dúvidas do cliente NESTE turno que ficarão pro consultor (não duplicar).",
    )
    ai_identity_asked: bool = False
    humano_solicitado: bool = False
