# Especificación de consentimiento rápido — borrador de producto y revisión legal

**Versión:** `consent-flow-1.0-engineering`  
**Estado:** implementación UAT sintética terminada; no es texto legal final y
no está aprobada para personas reales

La implementación y sus bloqueos están documentados en
[`docs/CONSENT_FLOW_V1.md`](../../docs/CONSENT_FLOW_V1.md).

## Tres actos separados

1. **Privacidad y evaluación:** tratamiento de datos para integrar y evaluar el
   expediente, con aviso integral enlazado.
2. **Acceso de proveedor:** autorización para conectar banco, fiscal, TPV u otra
   fuente específica. Las credenciales se capturan en el proveedor, no en Olin.
3. **Consulta a sociedad de información crediticia:** sección y artefacto
   separados, con el texto y firma aprobados por la Institución/Círculo.

No se agrupan en una casilla general. Marketing es un consentimiento opcional y
separado.

## Pantallas mínimas

### Pantalla 1 — propósito

> Usaremos los datos que elijas para preparar una evaluación de crédito para
> **[INSTITUCIÓN]**. Olin no garantiza un crédito y **[INSTITUCIÓN]** decide.
> Puedes continuar con otra evidencia cuando una ruta esté disponible.

Mostrar: responsable, finalidad, categorías de datos, fuente, destinatario,
retención resumida, derechos/retirada, enlace al aviso integral y versión.

### Pantalla 2 — selección de fuente

Mostrar una tarjeta por fuente con: qué se obtiene, qué no se obtiene, periodo,
si se actualiza, quién recibe, cómo revocar y alternativa disponible.

### Pantalla 3 — aceptación y autenticación

- casilla desmarcada;
- texto exacto y no editable;
- botón “Autorizar esta fuente”;
- OTP o proveedor de firma aprobado;
- recibo descargable y enviado al canal verificado.

### Pantalla 4 — resultado

Mostrar estado: conectado, incompleto, rechazado, expirado o retirado. Nunca
interpretar una conexión como aprobación crediticia.

## Artefacto de evidencia

Guardar de forma inmutable:

- `consent_id`, `purpose`, institución y fuente;
- versión de aviso y versión de autorización;
- texto completo o referencia de contenido inmutable más SHA-256;
- identidad/autoridad vinculada y método de verificación;
- fecha/hora UTC, canal, idioma, actor capturador;
- OTP/transacción o identificador del proveedor de firma;
- IP y agente de usuario sólo si fueron aprobados, minimizados y declarados;
- recibo, constancia de conservación aplicable y estado;
- retiro, motivo, actor y momento; y
- todos los accesos/ingestas vinculados al `consent_id`.

## Retirada

Un botón y un canal asistido permiten retirar el consentimiento. La retirada:

- bloquea nuevas conexiones e ingestas dependientes;
- cancela sesiones activas;
- abre una tarea de operación;
- no promete borrar registros que deban conservarse por obligación o defensa;
- informa qué tratamiento se detuvo y qué retención permanece, sujeto a revisión
  legal.

## Pruebas de aceptación

- ninguna casilla llega marcada;
- una versión nueva exige nuevo consentimiento cuando cambia la finalidad;
- el hash del texto puede reconstruirse;
- el OTP no puede reutilizarse y expira;
- retirar bloquea el siguiente webhook;
- un partner no puede ver consentimientos de otro tenant;
- la caída del proveedor no crea consentimiento ni evidencia falsa;
- el recibo coincide con el registro del servidor;
- la autorización de buró es separada;
- accesibilidad y español claro son aprobados por usuarios reales.

## Resultado de ingeniería — 28 agosto 2026

- implementado: políticas inmutables por finalidad y proveedor;
- implementado: identidad y facultad vinculadas desde fuentes confiables;
- implementado: OTP de un solo uso, expiración, cinco intentos y bloqueo;
- implementado: recibo canónico con SHA-256 y aislamiento por institución;
- implementado: retirada con cancelación de sesiones y tarea crítica de
  operaciones;
- implementado: autorización separada de buró antes de puntuar datos de buró;
- bloqueado: texto legal mexicano final, forma SIC, proveedor OTP/firma real,
  calendario de retención y decisión sobre NOM-151;
- prohibido: consentimiento sintético o texto directo en piloto/producción,
  salvo la bandera explícita y temporal de migración.
