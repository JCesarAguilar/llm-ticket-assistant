import csv
from common import config


def calculate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calcula el costo aproximado de una consulta al modelo basado en la cantidad de tokens.
    """
    cost_input = (prompt_tokens / 1000) * config.INPUT_PRICE_1K
    cost_output = (completion_tokens / 1000) * config.OUTPUT_PRICE_1K
    return round(cost_input + cost_output, 6)


def log_metrics(row: dict) -> None:
    """Agrega una fila a metrics/metrics.csv, escribiendo el header si el archivo no existe o está vacío."""
    config.METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)

    file_exists = (
        config.METRICS_PATH.exists() and config.METRICS_PATH.stat().st_size > 0
    )

    with open(config.METRICS_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
