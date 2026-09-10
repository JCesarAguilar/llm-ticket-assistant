import pytest
from pydantic import ValidationError

from common.schemas import TicketResponse
from common.metrics import calculate_cost


def test_calculate_cost_con_valores_conocidos():
    """1000 tokens de prompt y 1000 de completion deberían costar exactamente
    la suma de los dos precios por 1000 tokens, sin dividir de más ni de menos."""
    costo = calculate_cost(prompt_tokens=1000, completion_tokens=1000)
    assert costo == round(0.00015 + 0.0006, 6)


def test_calculate_cost_con_cero_tokens():
    """Sin tokens, el costo tiene que ser exactamente cero."""
    costo = calculate_cost(prompt_tokens=0, completion_tokens=0)
    assert costo == 0.0


def test_ticket_response_valida_json_correcto():
    """Un JSON con los tres campos bien formados se debe parsear sin error."""
    json_valido = (
        '{"answer": "Hacemos envios a todo el Peru.", '
        '"confidence": 0.9, '
        '"actions": ["responder_directamente"]}'
    )
    ticket = TicketResponse.model_validate_json(json_valido)

    assert ticket.answer == "Hacemos envios a todo el Peru."
    assert ticket.confidence == 0.9
    assert ticket.actions == ["responder_directamente"]


def test_ticket_response_rechaza_json_incompleto():
    """Si al modelo se le olvida un campo obligatorio (confidence), la validacion
    tiene que fallar en vez de dejarlo pasar silenciosamente."""
    json_incompleto = '{"answer": "Hacemos envios a todo el Peru.", "actions": ["responder_directamente"]}'

    with pytest.raises(ValidationError):
        TicketResponse.model_validate_json(json_incompleto)
