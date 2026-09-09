from enum import Enum

from pydantic import BaseModel, Field


class TicketAction(str, Enum):
    RESPONDER_DIRECTAMENTE = "responder_directamente"
    ESCALAR_A_HUMANO = "escalar_a_humano"
    SOLICITAR_MAS_INFORMACION = "solicitar_mas_informacion"
    MARCAR_URGENTE = "marcar_urgente"


class TicketResponse(BaseModel):
    answer: str = Field(min_length=1, description="Respuesta generada para el cliente.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Nivel de confianza del modelo en la respuesta, entre 0.0 y 1.0",
    )
    actions: list[TicketAction] = Field(
        min_length=1,
        description="Lista de acciones recomendadas para el agente, al menos una.",
    )
