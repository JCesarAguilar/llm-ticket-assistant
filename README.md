# LLM Ticket Assistant

Asistente de soporte al cliente para **Yolu**, una tienda peruana de zapatillas que
recibe consultas por redes sociales (Instagram, Facebook, TikTok y WhatsApp).

Recibe la pregunta de un cliente, la envía a la API de OpenAI aplicando una técnica de
prompt engineering (few-shot), y devuelve un JSON validado con la respuesta sugerida,
un nivel de confianza y las acciones recomendadas para el agente humano. Cada ejecución
queda registrada con sus métricas de tokens, latencia y costo estimado.

El asistente **no responde directamente al cliente**: genera un borrador para que un
agente humano lo revise, adapte y envíe.

---

## Requisitos

- Python 3.10 o superior (desarrollado y probado con Python 3.14.6)
- Una API key de OpenAI

---

## Instalación

```bash
git clone https://github.com/JCesarAguilar/llm-ticket-assistant.git
cd llm-ticket-assistant

python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# .\venv\Scripts\activate       # Windows

pip install -r requirements.txt
```

---

## Variables de entorno

El proyecto necesita una sola variable: `OPENAI_API_KEY`.

```bash
cp .env.example .env
```

Luego abre `.env` y coloca tu clave:

```
OPENAI_API_KEY=sk-...
```

La clave se obtiene en https://platform.openai.com/api-keys.
El archivo `.env` está incluido en `.gitignore`, por lo que nunca se sube al repositorio.
Si falta la variable, el programa se detiene al iniciar con un mensaje que indica cómo
solucionarlo.

---

## Uso

Desde la raíz del proyecto:

```bash
python -m src.run_query
```

El script pide una pregunta por consola y devuelve el JSON de respuesta:

```json
{
  "answer": "Sí, hacemos envíos a todo el Perú, incluyendo Arequipa. El tiempo estimado de entrega es de 3 a 5 días hábiles.",
  "confidence": 0.9,
  "actions": [
    "responder_directamente"
  ]
}
```

> **Importante:** ejecutar siempre desde la raíz del proyecto. Los módulos se importan
> como `common.*` y `src.*`, por lo que correr el script desde otra carpeta provoca un
> `ModuleNotFoundError`.

### Campos de la respuesta

| Campo | Tipo | Descripción |
|---|---|---|
| `answer` | string | Respuesta lista para que el agente la use o adapte. |
| `confidence` | float (0.0–1.0) | Qué tan seguro está el modelo de que la respuesta es correcta y completa. |
| `actions` | lista de strings | Acciones recomendadas para el agente. Al menos una. |

Acciones posibles: `responder_directamente`, `escalar_a_humano`,
`solicitar_mas_informacion`, `marcar_urgente`.

---

## Estructura del proyecto

```
common/
  config.py        # configuración: API key, modelo, precios, rutas
  schemas.py       # contrato de salida con Pydantic (answer, confidence, actions)
  llm.py           # comunicación con la API de OpenAI
  metrics.py       # cálculo de costo y registro de métricas en CSV
src/
  run_query.py     # orquestación del flujo + punto de entrada ejecutable
prompts/
  main_prompt.txt  # prompt de sistema con instrucciones, reglas y ejemplos few-shot
metrics/
  metrics.csv      # registro de métricas, una fila por ejecución
tests/
  test_core.py     # tests automatizados
pytest.ini         # configuración de pytest (rutas de importación)
```

La arquitectura separa responsabilidades en capas: configuración y contratos de datos
(`config.py`, `schemas.py`), servicios que hablan con el exterior (`llm.py` con la API,
`metrics.py` con el disco), y orquestación (`run_query.py`), que solo conecta las piezas
sin implementar detalles.

---

## Configuración del modelo

Definida en `common/config.py`:

| Parámetro | Valor | Justificación |
|---|---|---|
| `MODEL_NAME` | `gpt-4o-mini` | La tarea es clasificación y redacción breve, no requiere razonamiento complejo. Mantiene el costo bajo para poder iterar con muchas pruebas. |
| `TEMPERATURE` | `0.2` | Prioriza consistencia: la misma consulta debe producir prácticamente la misma clasificación. |
| `MAX_TOKENS` | `300` | El JSON de respuesta es corto (tres campos). Deja margen suficiente sin gastar de más. |

---

## Técnica de prompt engineering

Se usa **few-shot prompting**: el prompt de sistema (`prompts/main_prompt.txt`) incluye
las instrucciones, las reglas de negocio, el esquema JSON esperado y cinco ejemplos
resueltos de pregunta/respuesta que cubren los distintos tipos de caso (consulta simple,
reclamo por pedido no recibido, consulta sobre métodos de pago, reclamo urgente con
libro de reclamaciones, y solicitud incompleta que requiere más datos).

El detalle de por qué se eligió esta técnica y los resultados de las iteraciones están
documentados en `reports/PI_report_en.md`.

---

## Métricas

Cada ejecución agrega una fila a `metrics/metrics.csv`:

| Columna | Descripción |
|---|---|
| `timestamp` | Fecha y hora de la consulta en UTC (formato ISO 8601). |
| `tokens_prompt` | Tokens consumidos por el prompt enviado. |
| `tokens_completion` | Tokens generados en la respuesta. |
| `total_tokens` | Suma de ambos. |
| `latency_ms` | Tiempo que tardó la llamada a la API, en milisegundos. |
| `estimated_cost_usd` | Costo estimado de la consulta en dólares. |

### Cómo reproducir las métricas

1. Ejecuta `python -m src.run_query` tantas veces como consultas quieras registrar.
2. Cada ejecución agrega una fila al final de `metrics/metrics.csv`. Si el archivo no
   existe o está vacío, se escribe automáticamente la fila de encabezados.
3. Para empezar de cero, borra el contenido del archivo: el encabezado se regenera solo.

El costo se calcula en `common/metrics.py` con esta fórmula:

```
estimated_cost_usd = (tokens_prompt / 1000) * INPUT_PRICE_1K
                   + (tokens_completion / 1000) * OUTPUT_PRICE_1K
```

Los precios por cada 1000 tokens están definidos en `common/config.py` y corresponden a
las tarifas publicadas por OpenAI para `gpt-4o-mini`. Se calculan por separado porque los
tokens de salida cuestan cuatro veces más que los de entrada.

---

## Tests

```bash
pytest
```

Cuatro tests automatizados en `tests/test_core.py`:

- **Cálculo de costo** con valores conocidos (1000 tokens de cada tipo) y con cero tokens,
  para verificar que la fórmula divide correctamente entre 1000.
- **Validación del JSON**: un caso válido que debe parsearse sin error, y un caso al que
  le falta un campo obligatorio (`confidence`), que debe ser rechazado por Pydantic.

Los tests no consumen la API ni requieren conexión a internet: prueban únicamente lógica
local (cálculo y validación).

---

## Limitaciones conocidas

1. **El modelo no tiene acceso a datos reales del negocio.** Sus respuestas se generan
   generalizando desde los ejemplos del prompt. Puede afirmar políticas que no le fueron
   dadas de forma explícita: al preguntarle por envíos a Chile respondió que solo se
   envía dentro del Perú, dato que no aparece en ninguna parte del prompt.
2. **`confidence` es autorreportado por el modelo**, no una probabilidad calibrada
   estadísticamente. Sirve como señal relativa para priorizar revisión humana, no como
   medida de precisión real.
3. **Los precios están fijos en el código.** Si OpenAI modifica sus tarifas hay que
   actualizarlos manualmente en `common/config.py`. `estimated_cost_usd` es una
   estimación, no el monto facturado.
4. **Sin manejo explícito de errores de la API.** Se depende de los reintentos por
   defecto del SDK de OpenAI; un fallo de red o de autenticación propaga la excepción.
5. **Sin historial de conversación.** Cada consulta es independiente: el asistente no
   recuerda intercambios anteriores con el mismo cliente.
6. **Sin moderación ni manejo de prompts adversariales.** El bonus de seguridad no está
   implementado en esta versión.
7. **Probado en macOS con Python 3.14.** No se verificó el funcionamiento en Windows.
