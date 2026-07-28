import { useState } from "react";
import { AnimatePresence, MotionConfig } from "motion/react";

type Step = "intake" | "evidence" | "decision" | "outcome";

const steps: Array<{ id: Step; label: string }> = [
  { id: "intake", label: "1. Registro" },
  { id: "evidence", label: "2. Evidencia" },
  { id: "decision", label: "3. Recomendación" },
  { id: "outcome", label: "4. Resultado" },
];

export default function PilotWorkspace() {
  const [step, setStep] = useState<Step>("intake");
  const [consent, setConsent] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [partnerDecision, setPartnerDecision] = useState<"pending" | "approved" | "declined">("pending");

  const advance = () => {
    if (step === "intake") { setSubmitted(true); setStep("evidence"); return; }
    if (step === "evidence") { setStep("decision"); return; }
    if (step === "decision") { setStep("outcome"); return; }
    if (step === "outcome") { setCompleted(true); return; }
  };

  return (
    <MotionConfig reducedMotion="user">
      <div className="pilot-workspace">
        <div className="pilot-workspace__topline">
          <div><span className="pilot-workspace__eyebrow">Vista previa de Olin</span><h2>Piloto sombra / Caso OL-0241</h2></div>
          <span className="pilot-workspace__badge">DATOS SINTÉTICOS · SIN MOVIMIENTO DE DINERO</span>
        </div>
        <div className="pilot-workspace__steps" role="tablist" aria-label="Etapas del expediente">
          {steps.map((item, index) => (
            <button key={item.id} type="button" role="tab" aria-selected={step === item.id} className={step === item.id ? "is-active" : ""} onClick={() => setStep(item.id)}>
              <span>0{index + 1}</span>{item.label}
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <section key={step} className="pilot-workspace__panel">
            {step === "intake" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Registro del comercio</span><h3>Primero, un expediente verificable.</h3><p>Captura el negocio, el monto solicitado y el consentimiento antes de evaluar cualquier señal.</p></div>
              <div className="pilot-form">
                <label>Nombre del negocio<input value="Abarrotes La Esperanza" readOnly /></label>
                <label>Tipo de negocio<select defaultValue="abarrotes"><option value="abarrotes">Abarrotes</option><option value="taqueria">Taquería</option><option value="other">Otro microcomercio</option></select></label>
                <label>Monto solicitado<input value="MXN 20,000" readOnly /></label>
                <label>Ubicación<input value="Iztapalapa, CDMX" readOnly /></label>
              </div>
              <label className="pilot-consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> Confirmo que el comerciante autorizó el uso de la evidencia crediticia y operativa seleccionada para este piloto sombra.</label>
            </>}
            {step === "evidence" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Registro de evidencia</span><h3>Cada señal muestra su origen.</h3><p>La fuente, el estado de verificación y las limitaciones quedan visibles para el analista.</p></div>
              <div className="pilot-evidence-list"><div><strong>Círculo de Crédito</strong><span className="status status--pending">Consentimiento pendiente</span><small>Esta vista previa no consulta un buró real.</small></div><div><strong>Flujo bancario / Syncfy</strong><span className="status status--mock">Sandbox sintético</span><small>Patrón determinista de depósitos, solo para demostración.</small></div><div><strong>Compras a proveedores</strong><span className="status status--mock">Evidencia sintética</span><small>Representa un historial de compra; no está verificado.</small></div><div><strong>Identidad / INE</strong><span className="status status--missing">Faltante</span><small>Debe verificarse antes de cualquier operación real.</small></div></div>
            </>}
            {step === "decision" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Recomendación explicable</span><h3>Revisión por comité.</h3><p>Olin organiza la evidencia; la institución originadora conserva la decisión oficial.</p></div>
              <div className="pilot-score-grid"><div className="pilot-score-card pilot-score-card--hero"><span>Score Olin</span><strong>68.4</strong><small>IC 57.1–75.6 · cobertura 60%</small></div><div className="pilot-score-card"><span>Ruta</span><strong>Nivel 7</strong><small>C2 · D2 · S2</small></div><div className="pilot-score-card"><span>Acción sugerida</span><strong>Comité</strong><small>Revisar identidad y evidencia bancaria faltante.</small></div></div>
              <div className="pilot-reasons"><strong>¿Por qué esta ruta?</strong><ul><li>La capacidad de pago parece adecuada, pero usa evidencia sintética.</li><li>No se adjuntó un consentimiento Círculo ni una INE verificados.</li><li>Un expediente shadow nunca puede autorizar un desembolso.</li></ul></div>
            </>}
            {step === "outcome" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Comparación con la institución</span><h3>La decisión también se vuelve evidencia.</h3><p>Registra la decisión independiente de la institución para producir datos de aprendizaje utilizables.</p></div>
              <div className="pilot-outcome"><div><span>Recomendación Olin</span><strong>Comité</strong></div><div><span>Decisión de la institución</span><div className="pilot-choice-row"><button type="button" className={partnerDecision === "approved" ? "is-selected" : ""} onClick={() => setPartnerDecision("approved")}>Aprobar</button><button type="button" className={partnerDecision === "declined" ? "is-selected" : ""} onClick={() => setPartnerDecision("declined")}>Rechazar</button></div></div><div><span>Concordancia</span><strong>{partnerDecision === "pending" ? "Pendiente de la institución" : partnerDecision === "declined" ? "Registrada · ruta distinta" : "Registrada · ruta alineada"}</strong></div></div>
            </>}
          </section>
        </AnimatePresence>
        <div className="pilot-workspace__footer"><span>{completed ? "Vista previa terminada · ningún dato fue guardado" : submitted ? "Simulación local del expediente" : "Vista previa interactiva"}</span><button type="button" className="button button--signal" disabled={completed || (step === "intake" && !consent)} onClick={advance}>{completed ? "Terminada ✓" : step === "outcome" ? "Terminar vista previa" : step === "intake" ? "Simular expediente" : "Continuar"}<span aria-hidden="true">{completed ? "" : "→"}</span></button></div>
      </div>
    </MotionConfig>
  );
}
