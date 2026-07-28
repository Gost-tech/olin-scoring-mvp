# Olin + institución financiera: runbook de lanzamiento

Este documento responde a una pregunta concreta: si hoy llega un pequeño
negocio, el capital está disponible y todos los acuerdos con la institución
están firmados, ¿quién hace qué?

## Modelo recomendado para el primer lanzamiento

La institución financiera origina y fondea el crédito. Olin recibe un
expediente autorizado, organiza la evidencia y entrega una recomendación
explicable. La institución hace KYC, toma la decisión oficial, firma el
contrato, desembolsa, cobra y atiende reclamaciones.

Este modelo permite probar Olin sin mezclar desde el primer día software,
capital, cobranza y obligaciones de un prestamista.

Si Olin aporta su propio capital y Monex solo proporciona cuenta, TPV o
infraestructura de pagos, Olin pasa a operar como otorgante. Ese modelo no
puede activarse con el MVP actual: exige una estructura legal aprobada,
obligaciones PLD/AML, contratos de crédito, contabilidad de cartera,
cobranza, atención al cliente, reservas y controles de capital.

## Acuerdos que deben existir antes del primer caso real

1. Contrato comercial y alcance exacto del piloto.
2. Anexo de tratamiento, transferencia, retención y eliminación de datos.
3. Política de crédito y matriz RACI: quién recomienda, decide, contrata,
   desembolsa, cobra y resuelve una reclamación.
4. Consentimiento y aviso de privacidad aprobados por abogados mexicanos.
5. Especificación de API o proceso seguro para Círculo, banco, TPV y
   proveedores.
6. Reglas de liquidación TPV y autorización expresa para cualquier retención
   de pagos.
7. SLA, soporte, incidentes, continuidad y seguridad.
8. Economía del piloto: precio, comisión, impuestos y prohibición de incentivos
   que premien originar un caso malo.
9. Protocolo de resultados: campos, frecuencia, mora, pagos parciales,
   reestructuras y fecha de cierre.

Un contacto positivo o una reunión no sustituyen estos acuerdos.

## Qué ocurre cuando un negocio pide financiamiento

### 1. Registro del interesado

El operador captura nombre, contacto, tipo de negocio, antigüedad, monto,
destino del financiamiento y una descripción concreta del proyecto. No promete
aprobación ni fecha de desembolso.

Mensaje correcto:

> Olin organiza tu expediente para que una institución financiera pueda
> evaluarlo. La institución tomará la decisión y te presentará cualquier
> oferta.

### 2. Elegibilidad inicial

Se comprueba que el negocio entra en la política del socio: zona, actividad,
antigüedad, monto, uso permitido, identidad y documentos mínimos. Los sectores
excluidos o usos personales salen del flujo antes de consultar datos pagados.

### 3. Consentimiento y KYC

El negocio acepta el texto y aviso vigentes. La institución ejecuta la
identificación y las verificaciones regulatorias acordadas. Olin registra
versión, canal, actor y fecha; no sustituye el KYC de la institución.

### 4. Cuenta, TPV y evidencia

Según el caso, el negocio conecta o aporta:

- flujo bancario;
- liquidaciones y ventas TPV;
- compras a proveedores o facturas;
- Círculo de Crédito;
- antigüedad, domicilio y continuidad operativa.

Cada dato conserva fuente, fecha, referencia y estado de verificación. Un dato
declarado por el solicitante nunca se etiqueta como verificado.

### 5. Recomendación Olin

El backend crea el caso, ejecuta `scorecard.py` y muestra score, tier, DSCR,
cobertura, razones y faltantes. Un sector no calibrado no puede obtener
aprobación automática; se dirige a revisión de la institución.

### 6. Decisión y oferta

Un analista de la institución revisa el expediente, documenta su decisión y,
si corresponde, genera su propia oferta: monto, plazo, costo, calendario y
condiciones. La recomendación Olin no es una aprobación del crédito.

### 7. Firma y desembolso

La institución firma su contrato con el cliente y desembolsa a la cuenta
acordada. El MVP shadow de Olin no puede ejecutar este paso. Una futura versión
live solo lo habilita con credenciales separadas, doble control, idempotencia,
conciliación y límites.

### 8. Pago y cobranza

La institución cobra conforme al contrato. Una retención sobre liquidaciones
TPV solo se usa si está jurídicamente autorizada, explicada al cliente y
soportada por la infraestructura del socio. Pagos parciales, mora,
reestructuras y cancelaciones se registran como eventos distintos.

### 9. Resultado devuelto a Olin

La institución devuelve decisión, desembolso, calendario, pagos, mora,
reestructura y cierre. Olin conserva estos outcomes con definiciones estables
para que la cohorte sea analizable. Sin este paso no existe dataset de
entrenamiento útil.

## Tres rutas de evidencia

| Ruta | Negocios de ejemplo | Evidencia principal | Regla de seguridad |
|---|---|---|---|
| Inventario | retail, abarrotes, ferreterías | banco + proveedores + rotación | proveedor ausente permanece visible |
| TPV | restaurantes, salones, retail | liquidaciones + banco + estacionalidad | TPV no se confunde con utilidad |
| Flujo operativo | talleres, consultorios, profesionales | banco + facturas/actividad + antigüedad | revisión humana hasta calibración |

El tipo de negocio ayuda a elegir la ruta. No reemplaza la evidencia.

## Go / no-go técnico

La versión sintética está lista para demostrar el flujo. No está lista para
datos o dinero reales mientras falte cualquiera de estos elementos:

- ambiente de producción separado y base persistente cifrada;
- autenticación fuerte, roles y rotación de secretos;
- integraciones reales y especificaciones aprobadas por el socio;
- almacenamiento cifrado de documentos y política de retención;
- bitácoras, alertas, respaldos, monitoreo y respuesta a incidentes;
- prueba de penetración y revisión de seguridad;
- operación KYC, fraude, soporte y reclamaciones;
- motor de cartera, conciliación y contabilidad si circula dinero.

La séquence correcte est donc:

`demo sintética → 10 casos shadow → revisión conjunta → integraciones reales
en sandbox → piloto live limitado → decisión de escala`
