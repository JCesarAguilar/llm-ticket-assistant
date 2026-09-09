import csv
from datetime import datetime, timezone

from common import config
from common.llm import ask_llm
import common.schemas


def calculate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calcula el costo aproximado de una consulta al modelo basado en la cantidad de tokens.
    """
    cost_input = (prompt_tokens / 1000) * config.INPUT_PRICE_1K
    cost_output = (completion_tokens / 1000) * config.OUTPUT_PRICE_1K
    return round(cost_input + cost_output, 6)


def log_metrics(row: dict) -> None:
    """Agrega una fila a metrics/metrics.csv, escribiendo el header si el archivo no existe o está vacío."""
    file_exists = (
        config.METRICS_PATH.exists() and config.METRICS_PATH.stat().st_size > 0
    )

    with open(config.METRICS_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def run_query(question: str) -> common.schemas.TicketResponse:
    """
    Ejecuta una consulta al modelo, valida la respuesta, registra métricas y la devuelve.
    """
    raw = ask_llm(question)

    try:
        ticket_response = common.schemas.TicketResponse.model_validate_json(raw["content"])
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
