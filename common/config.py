import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError(
        "\nFalta OPENAI_API_KEY.\n"
        "Para arreglarlo:\n"
        "  1) Copia .env.example y renómbralo a .env\n"
        "  2) Pega tu clave en la línea OPENAI_API_KEY=\n"
        "  3) Consíguela en: https://platform.openai.com/api-keys\n"
    )


# Uso un modelo "mini" en vez del modelo grande porque esta tarea es
# clasificación simple (no necesita razonamiento complejo) y así
# mantengo el costo bajo para poder correr muchas pruebas.
MODEL_NAME = "gpt-4o-mini"

# Temperature baja porque quiero que el modelo sea consistente:
# la misma entrada debería dar (casi) siempre la misma clasificación.
TEMPERATURE = 0.2

# Mi respuesta es un JSON corto (2-3 campos), así que con 300 tokens
# sobra margen sin gastar de más si el modelo se extiende un poco.
MAX_TOKENS = 300

BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
PROMPT_PATH = BASE_DIR / "prompts" / "main_prompt.txt"
METRICS_PATH = BASE_DIR / "metrics" / "metrics.csv"

INPUT_PRICE_1K = 0.00015  # Precio por cada 1,000 tokens para gpt-4o-mini
OUTPUT_PRICE_1K = 0.0006  # Precio por cada 1,000 tokens para gpt-4o-mini
