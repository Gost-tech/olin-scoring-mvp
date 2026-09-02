# Anexo de datos de decisión y desempeño — borrador para revisión legal

**Documento:** `OLIN-MX-OUTCOME-DATA-V01`  
**Estado:** BORRADOR; NO APROBADO; NO FIRMAR SIN REVISIÓN LEGAL  
**Jurisdicción prevista:** México  
**Contrato principal:** Convenio de piloto sombra Olin

## 1. Partes y finalidad

Entre **[RAZÓN SOCIAL DE LA INSTITUCIÓN]** (“Institución”) y **[RAZÓN SOCIAL DE
OLIN]** (“Olin”), este Anexo define la devolución controlada de datos necesarios
para medir el flujo de trabajo y, posteriormente, analizar desempeño. Olin no
otorga crédito, no sustituye la decisión de la Institución y no podrá afirmar
desempeño predictivo con base exclusiva en los diez casos del piloto.

## 2. Identificador y minimización

La Institución asignará a cada expediente un identificador estable y
pseudonimizado. El archivo de resultados no incluirá nombre, teléfono, correo,
domicilio completo, credenciales bancarias ni documentos de identidad, salvo
que una finalidad aprobada y el acuerdo de datos exijan expresamente un campo.

## 3. Campos obligatorios

### 3.1 Decisión

- identificador de expediente;
- fecha y hora de decisión;
- decisión final: aprobado, rechazado, pendiente, cancelado o retirado;
- código de razón principal y hasta [N] razones secundarias;
- indicador de coincidencia con recomendación Olin;
- existencia de override, autoridad que lo aprobó y código de razón;
- monto, plazo y tasa finalmente ofrecidos, si aplica;
- evidencia faltante o excepción relevante.

### 3.2 Desempeño

- indicador de desembolso y fecha;
- saldo y estado al cierre de cada ventana acordada;
- días de atraso máximos y al corte;
- pago puntual, pago tardío, reestructura, castigo, fraude confirmado,
  recuperación y liquidación;
- fecha de cada evento y definición de política aplicada;
- monto recuperado y saldo final, cuando aplique.

## 4. Definiciones y ventana

Antes del primer caso, la Institución anexará su diccionario para “atraso”,
“incumplimiento”, “reestructura”, “fraude”, “castigo”, “recuperado” y “pagado”.
La ventana mínima será **[DÍAS; NO MENOR A 30]**, y la ventana de desempeño para
validación será **[DEFINIDA POR CRÉDITO/MODEL RISK]**. Los casos rechazados y
aprobados deberán incluirse para evitar que el conjunto de decisión quede
incompleto; el desempeño sólo existe cuando corresponda.

## 5. Entrega y calidad

- periodicidad: **[SEMANAL/MENSUAL]**;
- canal cifrado: **[SFTP/API/BUCKET APROBADO]**;
- responsable Institución: **[NOMBRE/CARGO]**;
- responsable Olin: **[NOMBRE/CARGO]**;
- plazo de corrección: **[X] días hábiles**;
- cada entrega incluirá versión de esquema, periodo, conteos, hash y registro de
  correcciones;
- una corrección no sobrescribirá silenciosamente el valor anterior: conservará
  valor previo, nuevo valor, razón, actor y momento.

## 6. Usos autorizados

Olin sólo usará los datos para: (a) reporte del piloto; (b) reconstrucción y
control de decisiones; y (c) análisis posterior expresamente aprobado. Olin no
entrenará ni ajustará un modelo, no reutilizará los datos para otra institución,
no venderá datos y no publicará resultados identificables sin autorización
escrita adicional.

## 7. Seguridad, retención y eliminación

Las partes incorporarán por referencia el anexo de seguridad y tratamiento de
datos. Se documentarán cifrado, control de acceso, registro de actores,
subencargados, ubicación, respuesta a incidentes, respaldo, retención,
devolución/eliminación y evidencia de destrucción. Las obligaciones legales de
conservación de la Institución no se transfieren automáticamente a Olin.

## 8. Incidentes y suspensión

La Institución u Olin suspenderá la transferencia ante exposición entre
instituciones, falta de consentimiento/autoridad, corrupción de historial,
evento severo de seguridad, uso no autorizado o discrepancia material no
resuelta. La reanudación requerirá evidencia de corrección y aprobación de los
responsables designados.

## 9. Reporte y derechos de referencia

El reporte conjunto separará métricas de proceso de cualquier análisis de
desempeño. El nombre, marca, testimonio o datos de la Institución sólo podrán
publicarse con aprobación escrita específica posterior.

## 10. Prelación y firmas

En caso de conflicto, **[DEFINIR PRELACIÓN CON CONTRATO PRINCIPAL/DPA]**. Los
representantes declaran contar con facultades suficientes. La firma electrónica
y conservación deberán seguir el método aprobado por las partes y su asesoría
legal.

**INSTITUCIÓN**  
Nombre: [REQUERIDO]  
Cargo: [REQUERIDO]  
Firma/fecha: [REQUERIDO]

**OLIN**  
Nombre: [REQUERIDO]  
Cargo: [REQUERIDO]  
Firma/fecha: [REQUERIDO]

## Preguntas obligatorias para el abogado

1. ¿La Institución y Olin son responsable/encargado, responsables independientes
   u otra relación por cada flujo?
2. ¿Qué bases, avisos, consentimientos y transferencias aplican a cada campo?
3. ¿Qué retenciones financieras, probatorias, fiscales o de prevención de lavado
   impiden la eliminación inmediata?
4. ¿Qué texto y evidencia necesita la autorización de Círculo y quién debe ser
   Usuario/Otorgante?
5. ¿Qué firma, autenticación y constancia NOM-151 son necesarias o prudentes?
