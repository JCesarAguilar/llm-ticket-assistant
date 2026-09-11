import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from common import config
from common.llm import client, SYSTEM_PROMPT


class SafetyResult(BaseModel):
    flagged: bool
    stage: Literal["pre", "post"]
    category: str
    action: Literal["block", "escalate", "allow"]
    detail: str


# --- Capa barata: patrones de inyección de prompt (corre antes de cualquier llamada a la API) ---
_INJECTION_PATTERNS = [
    r"ignor\w*\s+(tus|las|todas)?\s*instruccion",
    r"ignore\s+(your|previous|all)\s+instructions",
    r"olvida\s+(todo\s+lo\s+anterior|tus\s+instrucciones)",
    r"disregard\s+(the\s+)?(above|previous)",
    r"eres\s+ahora\b",
    r"you\s+are\s+now\b",
    r"act[uú]a\s+como\s+si",
    r"act\s+as\s+(if|a)\b",
    r"repite\s+(tu|el)\s+(system\s+)?prompt",
    r"reveal\s+your\s+(system\s+)?prompt",
    r"muestra\s+tus\s+instrucciones",
    r"cu[aá]les?\s+son\s+tus\s+instrucciones",
    r"nueva\s+regla\s*:",
    r"new\s+instructions?\s*:",
    r"modo\s+desarrollador",
    r"developer\s+mode",
    r"\bDAN\b",
]
_COMPILED_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS
]


# --- Redacción de PII antes de que cualquier texto entre a un log ---
_PII_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[TARJETA]"),
    (re.compile(r"\b\d{8,12}\b"), "[DOCUMENTO]"),
]


_MARCADOR_EJEMPLOS = "### EJEMPLOS ###"

# El detector de fuga deriva sus frases del prompt real, no de una copia a mano:
# si mañana editás main_prompt.txt, esto se actualiza solo.
if _MARCADOR_EJEMPLOS not in SYSTEM_PROMPT:
    raise ValueError(
        f"\nFalta el marcador {_MARCADOR_EJEMPLOS} en prompts/main_prompt.txt.\n"
        "Sin él, el detector de fuga compararía también contra los ejemplos few-shot\n"
        "y marcaría como fuga cualquier respuesta legítima.\n"
    )


def _lineas_de_instrucciones() -> list[str]:
    """Las líneas de la sección de instrucciones, que nunca deberían
    aparecer textuales en una respuesta al cliente. Se excluyen los
    ejemplos (esos SON las respuestas deseadas) y las líneas cortas
    (encabezados como 'Reglas:', demasiado genéricos para decidir)."""
    instrucciones = SYSTEM_PROMPT.split(_MARCADOR_EJEMPLOS)[0]
    lineas = []
    for linea in instrucciones.splitlines():
        limpia = linea.strip().lstrip("-").strip()
        if len(limpia) >= 30:
            lineas.append(limpia.lower())
    return lineas


_LINEAS_DE_INSTRUCCIONES = _lineas_de_instrucciones()


def redact_pii(text: str) -> str:
    """Reemplaza patrones conocidos de datos sensibles antes de loguear texto.
    Igual limitación que los patrones de inyección: reduce el riesgo, no lo elimina."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _truncate(text: str, max_chars: int = 300) -> str:
    """Evita que un mensaje larguísimo (o un intento de ataque) infle el log."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


def _safe_snippet(text: str) -> str:
    """Pipeline completo antes de que texto de usuario entre a un log: truncar y redactar."""
    return redact_pii(_truncate(text))


def _matches_injection(text: str) -> str | None:
    for pattern in _COMPILED_INJECTION_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


def new_trace_id() -> str:
    """Id corto para correlacionar la fila de metrics.csv con las de
    security_log.csv que pertenecen a la misma consulta."""
    return uuid.uuid4().hex[:12]


def check_input(question: str) -> SafetyResult:
    """Corre antes de llamar al modelo principal."""
    moderation = client.moderations.create(input=question)
    result = moderation.results[0]

    if result.flagged:
        flagged_categories = [
            name for name, value in result.categories.model_dump().items() if value
        ]
        return SafetyResult(
            flagged=True,
            stage="pre",
            category="harmful_content",
            action="block",
            detail=f"Moderation API en la pregunta ({', '.join(flagged_categories)}): {_safe_snippet(question)}",
        )

    matched = _matches_injection(question)
    if matched:
        return SafetyResult(
            flagged=True,
            stage="pre",
            category="prompt_injection",
            action="escalate",
            detail=f"Patrón sospechoso '{matched}': {_safe_snippet(question)}",
        )

    return SafetyResult(
        flagged=False, stage="pre", category="none", action="allow", detail=""
    )


def check_output(answer: str, confidence: float) -> SafetyResult:
    """Corre después de tener la respuesta validada. Modera la respuesta
    generada y revisa que el modelo no esté repitiendo sus instrucciones.

    Revisamos solo `answer` (lo que llega al cliente), no el JSON crudo:
    el andamiaje del JSON coincide con el esquema del prompt por diseño."""

    moderation = client.moderations.create(input=answer)
    result = moderation.results[0]

    if result.flagged:
        flagged_categories = [
            name for name, value in result.categories.model_dump().items() if value
        ]
        return SafetyResult(
            flagged=True,
            stage="post",
            category="harmful_content",
            action="block",
            detail=f"Moderation API en la respuesta ({', '.join(flagged_categories)}): {_safe_snippet(answer)}",
        )

    answer_lower = answer.lower()
    for linea in _LINEAS_DE_INSTRUCCIONES:
        if linea in answer_lower:
            return SafetyResult(
                flagged=True,
                stage="post",
                category="prompt_leak",
                action="escalate",
                detail=f"La respuesta repite una línea de las instrucciones: '{_truncate(linea, 80)}'",
            )

    if confidence == 0.0:
        return SafetyResult(
            flagged=True,
            stage="post",
            category="model_refusal",
            action="escalate",
            detail="confidence == 0.0: posible señal informal de negativa del modelo.",
        )

    return SafetyResult(
        flagged=False, stage="post", category="none", action="allow", detail=""
    )


def log_security_event(result: SafetyResult, trace_id: str) -> None:
    """Agrega una fila a security/security_log.csv. Mismo patrón que log_metrics()."""
    import csv

    config.SECURITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_exists = (
        config.SECURITY_LOG_PATH.exists()
        and config.SECURITY_LOG_PATH.stat().st_size > 0
    )

    row = {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": result.stage,
        "category": result.category,
        "action": result.action,
        "detail": result.detail,
    }

    with open(config.SECURITY_LOG_PATH, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
