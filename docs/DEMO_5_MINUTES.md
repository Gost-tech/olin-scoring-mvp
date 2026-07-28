# Demostración Olin en cinco minutos

Objetivo: demostrar un producto de decisión, no simular un préstamo.

Datos: exclusivamente los tres escenarios sintéticos de la cohorte
`demo_sintetica_01`. Ningún movimiento de dinero es posible.

## 0:00–0:40 — El problema

“Una institución recibe expedientes incompletos de pequeños comercios. Olin
organiza la evidencia, evalúa capacidad de pago y continuidad operativa, y
produce una recomendación explicable. La institución conserva la decisión.”

Mostrar la file y las tres rutas reales:

- La Esperanza: ruta de aprobación;
- San Miguel: revisión requerida;
- La Unión: no recomendar.

## 0:40–1:40 — Crear el expediente

1. Abrir `Nuevo expediente`.
2. Mostrar cohorte, referencia del socio y consentimiento.
3. Explicar que cada fuente tiene estado, referencia y verificación.
4. Enviar el expediente sintético.

Frase clave: “El frontend no inventa la decisión. El backend persiste el
expediente y ejecuta `scorecard.py`.”

## 1:40–3:10 — Revisar evidencia y recomendación

1. Volver a la mesa de decisión.
2. Abrir `Abarrotes San Miguel`.
3. Mostrar Círculo, DSCR, score, cobertura y fuentes.
4. Distinguir claramente:
   - recomendación Olin;
   - decisión independiente de la institución.

Frase clave: “Olin no promete el reembolso. Hace visibles las razones, la
evidencia faltante y la capacidad observada.”

## 3:10–4:20 — Acción del analista

1. Guardar una nota breve.
2. Seleccionar `Solicitar evidencia`.
3. Registrar un motivo.
4. Recargar la página y comprobar que la acción persiste.

## 4:20–5:00 — Resultado del piloto

Mostrar la barra de cohorte:

- consentimiento registrado;
- Banco y compras verificadas;
- decisión de la institución;
- concordancia observable.

Cerrar con: “El próximo paso no es prestar. Es procesar diez expedientes
autorizados, medir tiempo de revisión, evidencia faltante y concordancia, y
decidir con el socio si existe valor operativo.”

## Preguntas para el socio

1. ¿Qué evidencia recibe hoy el analista y en qué formato?
2. ¿Qué dato suele bloquear o retrasar una decisión?
3. ¿Quién debe crear el expediente y quién registra la decisión final?
4. ¿Qué integración existe para liquidaciones TPV?
5. ¿Puede retenerse un porcentaje de las liquidaciones para una fase futura?
