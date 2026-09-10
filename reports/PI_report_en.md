# Proyecto Integrador Módulo 1 — Reporte técnico

**Proyecto:** LLM Ticket Assistant — asistente de soporte para Yolu (tienda peruana de zapatillas)
**Autor:** Julio César Aguilar
**Repositorio:** https://github.com/JCesarAguilar/llm-ticket-assistant

---

## 1. Objetivo y alcance

El sistema recibe una consulta de un cliente llegada por redes sociales, la envía a la API
de OpenAI aplicando few-shot prompting, y devuelve un JSON validado con tres campos:
`answer` (respuesta sugerida), `confidence` (0.0–1.0) y `actions` (acciones recomendadas
para el agente). Cada ejecución registra tokens, latencia y costo estimado.

La decisión de diseño más importante es que el asistente **no automatiza la respuesta al
cliente**: produce un borrador para revisión humana. Esto acota el riesgo de alucinación a
un error de borrador, no a un error enviado al cliente.

## 2. Arquitectura

El proyecto separa responsabilidades en capas, con dependencias que fluyen en una sola
dirección (la orquestación depende de los servicios; los servicios dependen de la
configuración y los contratos; nunca al revés):

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Configuración | `common/config.py` | API key, modelo, parámetros, precios, rutas. |
| Contratos | `common/schemas.py` | Esquema de salida con Pydantic y enum de acciones válidas. |
| Servicio externo | `common/llm.py` | Única pieza que habla con la API de OpenAI. Mide latencia y devuelve tokens en crudo. |
| Servicio interno | `common/metrics.py` | Cálculo de costo y persistencia de métricas en CSV. |
| Orquestación | `src/run_query.py` | Conecta las piezas: consulta, valida, calcula, registra. No implementa detalles. |

El criterio para esta separación fue la razón de cambio de cada pieza: si OpenAI modifica
sus precios se toca solo `metrics.py`/`config.py`; si el formato de registro pasa de CSV a
base de datos, solo `metrics.py`; si cambia el flujo, solo `run_query.py`. Una señal
concreta de que la separación quedó correcta es que `import csv` desapareció del
orquestador: dejó de conocer detalles de almacenamiento que no le correspondían.

La validación es un punto explícito del diseño: la respuesta del modelo llega como texto
plano y se convierte a objeto con `TicketResponse.model_validate_json()`. Si el modelo
devuelve un JSON mal formado o incompleto, la ejecución falla con un error claro en lugar
de propagar datos inválidos hacia el resto del sistema.

## 3. Técnica de prompt engineering: few-shot

Se eligió **few-shot prompting** (cinco ejemplos resueltos dentro del prompt de sistema)
frente a las otras dos opciones disponibles, por tres razones:

1. **La tarea exige un formato de salida rígido.** El contrato de salida es un JSON con
   tres campos, uno de ellos restringido a un enum de cuatro valores. Los ejemplos
   resueltos comunican ese formato con mucha más fidelidad que una descripción en prosa.
2. **Las reglas de negocio son de calibración, no de razonamiento.** Decisiones como
   "bajar el confidence ante un reclamo" o "no inventar stock exacto" se transmiten mejor
   mostrando casos resueltos que explicándolas de forma abstracta. La evidencia de esto
   está en la sección 5.
3. **Costo y latencia.** Chain-of-thought agregaría tokens de razonamiento intermedio que
   el agente humano no necesita ver, y self-consistency multiplicaría el costo por el
   número de llamadas para votar una respuesta — desproporcionado en una tarea donde las
   reglas son explícitas y la salida es corta.

Los cinco ejemplos cubren deliberadamente casos distintos: consulta simple resoluble,
reclamo por pedido no recibido, consulta sobre métodos de pago, reclamo urgente con
mención al libro de reclamaciones, y solicitud incompleta que requiere pedir más datos.

## 4. Resumen de métricas

Siete ejecuciones registradas en `metrics/metrics.csv`:

| Métrica | Mín | Máx | Promedio |
|---|---|---|---|
| `tokens_prompt` | 546 | 615 | 569 |
| `tokens_completion` | 35 | 57 | 50 |
| `total_tokens` | 581 | 666 | 619 |
| `latency_ms` | 2 395 | 4 923 | 3 299 |
| `estimated_cost_usd` | 0.000103 | 0.000123 | 0.000115 |

Costo acumulado de las siete consultas: **0.000807 USD**. Proyección a 1 000 consultas:
**≈ 0.115 USD**, un orden de magnitud que hace viable el caso de uso incluso a volumen
alto de tickets.

Observaciones sobre los datos:

- **El prompt domina el costo.** Con un promedio de 569 tokens de entrada contra 50 de
  salida, el prompt de sistema representa más del 90 % de los tokens consumidos. Como es
  fijo en todas las consultas, es el objetivo natural de cualquier optimización de costo.
- **La primera llamada fue la más lenta** (4 923 ms contra una mediana de 3 299 ms), lo
  que sugiere sobrecarga inicial de conexión más que variabilidad del modelo.
- **La muestra es pequeña (n = 7)** y todas las consultas se ejecutaron en la misma
  sesión, por lo que estas cifras son indicativas, no estadísticamente representativas.

## 5. Desafíos encontrados

**Una acción del esquema nunca se activaba.** Tras las primeras pruebas, `actions` jamás
devolvía `solicitar_mas_informacion`, aunque el enum la incluía. La causa no fue un error
de código: el prompt tenía la regla escrita en prosa ("si no tienes información
suficiente, dilo explícitamente"), pero ningún ejemplo que la mostrara resuelta. Ante la
consulta deliberadamente incompleta *"quiero cambiar mi pedido por otro modelo"*, el
modelo respondió pidiendo el número de pedido —el comportamiento correcto— pero la
etiquetó como `responder_directamente`. El contenido era adecuado; la clasificación, no.

Al agregar un quinto ejemplo few-shot que modelaba explícitamente ese caso, la misma
consulta pasó a devolver `solicitar_mas_informacion` con confidence 0.7. Una segunda
prueba con otra redacción (*"cambiar el color de mi pedido"*) devolvió una respuesta
adaptada al contexto —pidió el color, no el modelo—, confirmando generalización real y no
memorización del ejemplo.

Este cambio tiene un costo medible: los tokens de prompt subieron de ~551 a ~614 por
consulta (+11 %), visible en las dos últimas filas del CSV. Es el precio concreto de la
mejora, y ejemplifica el trade-off central del few-shot: cada ejemplo agregado mejora la
fidelidad del formato y encarece todas las consultas futuras.

**Colisión semántica en la escala de confidence.** El prompt establecía "confidence ≤ 0.6
ante un reclamo". Al asignar 0.6 también a los casos de información faltante, dos
situaciones de gravedad muy distinta quedaban en el mismo rango, y cualquier lógica de
enrutamiento basada en umbrales las habría tratado igual. Se resolvió reservando 0.5 y
menos para reclamos, 0.7 para información faltante y 0.9 para respuestas resueltas, y
estableciendo que el enrutamiento debe decidirse por el campo `actions` —diseñado
justamente para eso— y no por el umbral de confidence.

**El modelo afirma políticas que no se le proporcionaron.** Ante *"¿hacen envíos a
Chile?"* respondió que solo se realizan envíos dentro del Perú, con confidence 0.7. Es una
inferencia razonable (ningún ejemplo menciona envíos internacionales) y falla en la
dirección segura —niega una capacidad en lugar de prometerla—, pero el dato no está en
ninguna parte del prompt. Muestra el límite del enfoque: sin acceso a datos reales del
negocio, el modelo rellena vacíos por generalización, y la regla en prosa de "no inventar
información" no cubre este tipo de inferencia por ausencia.

**Error de unidad en el cálculo de costo.** La primera implementación multiplicaba el
número de tokens directamente por el precio por 1 000 tokens, arrojando costos 1 000 veces
mayores a los reales. El error pasaba desapercibido porque el resultado seguía siendo un
número plausible a simple vista. Motivó el test que verifica el cálculo con valores
conocidos (1 000 tokens de cada tipo), comparados contra un resultado calculado a mano y
no contra la salida del propio código.

## 6. Mejoras posibles

1. **RAG sobre datos reales del negocio** (stock, precios vigentes, cobertura de envíos).
   Es la mejora de mayor impacto: elimina la raíz del problema descrito en la sección 5,
   ya que el modelo dejaría de generalizar sobre políticas y respondería con información
   recuperada y verificable.
2. **Capa de moderación y prompts adversariales** (`src/safety.py`, bonus no implementado):
   detección de intentos de manipulación del prompt y registro de las decisiones tomadas.
3. **Calibración del confidence.** Hoy es autorreportado por el modelo, no una
   probabilidad medida. Con un conjunto de consultas etiquetadas por un agente humano se
   podría comparar el confidence declarado contra el acierto real y verificar si la escala
   significa algo.
4. **Manejo explícito de errores de API**, con reintentos y timeouts propios en lugar de
   depender de los valores por defecto del SDK.
5. **Endpoint HTTP e historial de conversación**, para integración real con la plataforma
   de tickets y seguimiento de intercambios sucesivos con el mismo cliente.
6. **Evaluación por lotes.** Un script que corra N consultas de una batería fija y compare
   resultados entre ejecuciones permitiría medir consistencia real: `temperature = 0.2`
   reduce la variabilidad, pero no la elimina.
