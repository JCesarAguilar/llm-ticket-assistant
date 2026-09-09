import time
from openai import OpenAI

from common import config

client = OpenAI(api_key=config.OPENAI_API_KEY)

with open(config.PROMPT_PATH, encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()


def ask_llm(prompt: str) -> dict:
    """
    Envía un prompt al modelo y devuelve el texto de respuesta
    junto con los datos crudos que se necesitan para las métricas
    (tokens y latencia). No valida ni parsea el JSON — eso lo hace
    quien llama a esta función.
    """

    start_time = time.perf_counter()

    response = client.chat.completions.create(
        model=config.MODEL_NAME,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    latency_ms = (time.perf_counter() - start_time) * 1000

    if response.usage is None:
        raise RuntimeError("La respuesta de OpenAI no incluyó datos de uso (tokens).")

    return {
        "content": response.choices[0].message.content,
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
        "latency_ms": latency_ms,
    }
