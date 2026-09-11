# Proyecto Integrador Módulo 1 — Reporte técnico

**Proyecto:** LLM Ticket Assistant — asistente de soporte para Yolu (tienda peruana de zapatillas)
**Autor:** Julio César Aguilar
**Repositorio:** https://github.com/JCesarAguilar/llm-ticket-assistant

---

## 1. Objetivo y arquitectura

El sistema recibe una consulta de un cliente llegada por redes sociales, la envía a la API
de OpenAI aplicando few-shot prompting, y devuelve un JSON validado (`answer`,
`confidence`, `actions`), registrando tokens, latencia y costo por ejecución. El asistente
**no responde directamente al cliente**: genera un borrador para revisión humana, lo que
acota el riesgo de alucinación a un error de borrador, no a un error enviado.

El proyecto separa responsabilidades en capas, con dependencias en una sola dirección:

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Configuración | `common/config.py` | API key, modelo, parámetros, precios, rutas. |
| Contratos | `common/schemas.py` | Esquema de salida (Pydantic) y enum de acciones. |
| Servicio externo | `common/llm.py` | Habla con la API de OpenAI; mide latencia. |
| Servicio interno | `common/metrics.py` | Calcula costo y persiste métricas en CSV. |
| Orquestación | `src/run_query.py` | Conecta las piezas; no implementa detalles. |

El criterio de separación fue la razón de cambio de cada pieza (precio de OpenAI → solo
`config.py`; formato de registro → solo `metrics.py`). La respuesta del modelo llega como
texto plano y se valida con `TicketResponse.model_validate_json()`: si el JSON es inválido
o incompleto, la ejecución falla con un error claro en vez de propagar datos corruptos.

## 2. Técnica de prompt engineering: few-shot

Se eligió few-shot (cinco ejemplos resueltos en el prompt de sistema) sobre chain-of-thought
o self-consistency por tres razones: el contrato de salida es un JSON rígido que los
ejemplos comunican mejor que una descripción en prosa; las reglas de negocio ("bajar
confidence ante un reclamo", "no inventar stock exacto") son de calibración, no de
razonamiento, y se transmiten mejor mostrando casos resueltos (evidencia en sección 4); y
chain-of-thought/self-consistency habrían agregado tokens o llamadas innecesarias para una
tarea con reglas explícitas y salida corta.

## 3. Resumen de métricas

Siete ejecuciones registradas en `metrics/metrics.csv`:

| Métrica | Mín | Máx | Promedio |
|---|---|---|---|
| `tokens_prompt` | 546 | 615 | 569 |
| `latency_ms` | 2 395 | 4 923 | 3 299 |
| `estimated_cost_usd` | 0.000103 | 0.000123 | 0.000115 |

Con ~569 tokens de entrada contra ~50 de salida, el prompt fijo representa más del 90 % del
costo por consulta — proyección a 1000 consultas: ≈ 0.115 USD. Muestra pequeña (n=7), cifras
indicativas, no estadísticamente representativas.

## 4. Desafíos encontrados

**Una acción del esquema nunca se activaba.** `solicitar_mas_informacion` no aparecía pese
a estar en el enum: la regla vivía en prosa, sin ejemplo que la modelara. Ante *"quiero
cambiar mi pedido por otro modelo"*, el modelo pidió los datos correctos pero lo etiquetó
como `responder_directamente`. Al agregar un quinto few-shot que modelaba el caso, la misma
consulta pasó a clasificarse correctamente, y una segunda prueba con otra redacción
("cambiar el color") confirmó generalización real, no memorización. Costo medible: los
tokens de prompt subieron ~11 % (551→614) al agregar el ejemplo — el trade-off central del
few-shot.

**Colisión de confidence.** Reservar `confidence ≤ 0.6` tanto para reclamos como para
información faltante habría confundido dos gravedades distintas bajo cualquier lógica de
umbral. Se resolvió separando rangos (0.5 reclamos, 0.7 falta de información, 0.9 resuelto)
y estableciendo que el enrutamiento debe decidirse por `actions`, no por confidence.

**El modelo generaliza sin datos reales.** Ante *"¿hacen envíos a Chile?"* afirmó que solo
se envía dentro del Perú — dato no presente en el prompt, inferido por ausencia. Falla en
la dirección segura, pero muestra el límite de fondo: sin acceso a datos reales del
negocio, el modelo rellena vacíos.

**Robustez bajo ataque adversarial.** Se probaron cinco mensajes maliciosos contra el
sistema tal como estaba: inyección directa ("ignora tus instrucciones"), extracción del
prompt de sistema, ruptura forzada de formato, ingeniería social (identidad falsa + pretexto
interno) y groserías dirigidas a la tienda.

| Ataque | Contenido resistido | Clasificación correcta | Rastro en métricas |
|---|---|---|---|
| Inyección directa | Sí | Sí | No |
| Extracción del prompt | Sí | No (`responder_directamente`) | No |
| Ruptura de formato | Sí | No (`confidence: 0.0` + `responder_directamente`) | No |
| Ingeniería social | Sí | Sí | No |
| Groserías | N/A (respuesta empática) | Ambigua (política no definida) | No |

Resultado: el contenido resistió 4/4 intentos de manipulación (ninguno logró que el modelo
afirmara algo falso o filtrara el prompt) — la combinación de reglas explícitas contra
inventar información y de que el humano revisa antes de enviar resultó efectiva. Pero la
clasificación fue inconsistente (2/4 quedaron marcados como envío directo al cliente) y
ningún ataque dejó registro distinguible de una consulta normal en `metrics.csv`. El sistema
se defiende pero es ciego a que fue atacado — la brecha real no es de contenido, es de
observabilidad. Un hallazgo colateral útil: `confidence: 0.0` emergió en 3 de 4 casos como
señal informal de "no puedo/no debo responder esto", sin estar documentado en la escala.

## 5. Mejoras posibles

1. **Detección y logging de eventos de seguridad** (`common/safety.py`, no implementado):
   moderación antes de llamar al modelo principal, y un registro auditable de intentos de
   manipulación — resuelve directamente la brecha de observabilidad de la sección 4.
2. **RAG sobre datos reales del negocio**: elimina la causa de fondo de las respuestas
   generalizadas sin verificar (envíos, stock, precios).
3. **Formalizar `confidence: 0.0`** como parte oficial de la escala, ya que el modelo lo usa
   de forma consistente sin que esté documentado.
4. **Calibración del confidence** contra etiquetas de un agente humano, y manejo explícito
   de errores de red/API en lugar de depender de los defaults del SDK.

## 6. Uso de asistencia de IA

Se usó Claude (Anthropic) como asistente técnico durante todo el desarrollo, en formato de
mentoría guiada: el autor implementó y ejecutó cada cambio; la IA revisó código ya escrito,
explicó conceptos bajo pedido y propuso diseños que el autor evaluó y aplicó.

Ejemplos concretos de prompts y su influencia: *"revisa mi config, dame feedback"* llevó a
detectar precios duplicados con nombres distintos y a restaurar un mensaje de error guiado
para `OPENAI_API_KEY` faltante. *"¿por qué bajar la confianza a 0.6, no se confunde con
escalar a humano?"* — pregunta del autor — motivó separar los rangos de confidence por tipo
de caso (sección 4). *"ayúdame a comprender el flujo y hazme preguntas para comprobar si lo
tengo claro"* generó una ronda de verificación conceptual (orden de ejecución de imports,
frontera entre texto y objeto validado, independencia entre prompt y schema) antes de dar
por cerrado el módulo principal. Las cinco pruebas adversariales de la sección 4 se
diseñaron y ejecutaron interactivamente: la IA propuso los mensajes de ataque, el autor los
corrió contra el sistema real y ambos interpretaron los resultados juntos.

Todo el código fue escrito y verificado por el autor (incluyendo la corrección de bugs
propios detectados en revisión, como el error de unidad en `calculate_cost` o el
desempaquetado incorrecto de un diccionario como tupla). La IA no tomó decisiones de diseño
de forma autónoma: las propuso, y el autor las aceptó, ajustó o rechazó con justificación
propia en cada caso.
