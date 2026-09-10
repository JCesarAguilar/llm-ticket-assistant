from datetime import datetime, timezone

from common.metrics import calculate_cost, log_metrics
from common.llm import ask_llm
import common.schemas


def run_query(question: str) -> common.schemas.TicketResponse:
    """
    Ejecuta una consulta al modelo, valida la respuesta, registra métricas y la devuelve.
    """
    raw = ask_llm(question)

    try:
        ticket_response = common.schemas.TicketResponse.model_validate_json(
            raw["content"]
        )
    except ValueError as e:
        raise ValueError(f"El modelo no devolvió un JSON válido: {e}")

    cost = calculate_cost(raw["prompt_tokens"], raw["completion_tokens"])

    log_metrics(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tokens_prompt": raw["prompt_tokens"],
            "tokens_completion": raw["completion_tokens"],
            "total_tokens": raw["total_tokens"],
            "latency_ms": round(raw["latency_ms"], 2),
            "estimated_cost_usd": cost,
        }
    )

    return ticket_response


if __name__ == "__main__":
    question = input("Ingrese su pregunta: ")
    response = run_query(question)
    print(response.model_dump_json(indent=2))
