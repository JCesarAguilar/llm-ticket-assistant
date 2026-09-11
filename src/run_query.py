from datetime import datetime, timezone

from common.metrics import calculate_cost, log_metrics
from common.llm import ask_llm
from src.safety import check_input, check_output, log_security_event, new_trace_id
from common.schemas import TicketAction, TicketResponse


def _fallback_response() -> TicketResponse:
    """Respuesta segura cuando un chequeo de seguridad bloquea la consulta."""
    return TicketResponse(
        answer="Esta consulta no pudo procesarse automáticamente por motivos de seguridad. Un agente la revisará.",
        confidence=0.0,
        actions=[TicketAction.ESCALAR_A_HUMANO],
    )


def _log_query_metrics(trace_id: str, raw: dict) -> None:
    cost = calculate_cost(raw["prompt_tokens"], raw["completion_tokens"])
    log_metrics(
        {
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tokens_prompt": raw["prompt_tokens"],
            "tokens_completion": raw["completion_tokens"],
            "total_tokens": raw["total_tokens"],
            "latency_ms": round(raw["latency_ms"], 2),
            "estimated_cost_usd": cost,
        }
    )


def run_query(question: str) -> TicketResponse:
    """
    Ejecuta una consulta al modelo, valida la respuesta, corre los
    chequeos de seguridad, registra métricas y la devuelve.
    """
    trace_id = new_trace_id()

    safety_pre = check_input(question)
    if safety_pre.flagged:
        log_security_event(safety_pre, trace_id)
        if safety_pre.action == "block":
            return _fallback_response()

    raw = ask_llm(question)

    try:
        ticket_response = TicketResponse.model_validate_json(raw["content"])
    except ValueError as e:
        raise ValueError(f"El modelo no devolvió un JSON válido: {e}")

    safety_post = check_output(ticket_response.answer, ticket_response.confidence)
    if safety_post.flagged:
        log_security_event(safety_post, trace_id)
        if safety_post.action == "block":
            _log_query_metrics(trace_id, raw)
            return _fallback_response()

    if safety_pre.flagged or safety_post.flagged:
        if TicketAction.ESCALAR_A_HUMANO not in ticket_response.actions:
            ticket_response.actions.append(TicketAction.ESCALAR_A_HUMANO)

    _log_query_metrics(trace_id, raw)

    return ticket_response


if __name__ == "__main__":
    question = input("Ingrese su pregunta: ")
    response = run_query(question)
    print(response.model_dump_json(indent=2))
