import { useState } from "react";
import { AnimatePresence, MotionConfig } from "motion/react";

type Step = "intake" | "evidence" | "decision" | "outcome";

const steps: Array<{ id: Step; label: string }> = [
  { id: "intake", label: "1. Intake" },
  { id: "evidence", label: "2. Evidence" },
  { id: "decision", label: "3. Decision" },
  { id: "outcome", label: "4. Pilot record" },
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
          <div><span className="pilot-workspace__eyebrow">Olin workspace</span><h2>Shadow pilot / Case OL-0241</h2></div>
          <span className="pilot-workspace__badge">SYNTHETIC DEMO · NO MONEY MOVES</span>
        </div>
        <div className="pilot-workspace__steps" role="tablist" aria-label="Pilot case steps">
          {steps.map((item, index) => (
            <button key={item.id} type="button" role="tab" aria-selected={step === item.id} className={step === item.id ? "is-active" : ""} onClick={() => setStep(item.id)}>
              <span>0{index + 1}</span>{item.label}
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <section key={step} className="pilot-workspace__panel">
            {step === "intake" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Merchant intake</span><h3>Start with a real question.</h3><p>Capture the business, requested amount and consent before any signal is evaluated.</p></div>
              <div className="pilot-form">
                <label>Business name<input value="Abarrotes La Esperanza" readOnly /></label>
                <label>Business type<select defaultValue="abarrotes"><option value="abarrotes">Abarrotes</option><option value="taqueria">Taquería</option><option value="other">Other small business</option></select></label>
                <label>Requested amount<input value="MXN 20,000" readOnly /></label>
                <label>Location<input value="Iztapalapa, CDMX" readOnly /></label>
              </div>
              <label className="pilot-consent"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /> I have the merchant's permission to use the selected credit and operating evidence for this shadow pilot.</label>
            </>}
            {step === "evidence" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Evidence ledger</span><h3>Nothing is hidden.</h3><p>Each signal has a source, a status and a clear limitation.</p></div>
              <div className="pilot-evidence-list"><div><strong>Círculo de Crédito</strong><span className="status status--pending">Consent required</span><small>No bureau response is connected in this demo.</small></div><div><strong>Bank cash flow / Syncfy</strong><span className="status status--mock">Mock sandbox</span><small>Deterministic deposit pattern for demonstration only.</small></div><div><strong>FMCG purchases</strong><span className="status status--mock">Mock evidence</span><small>Supplier history is represented, not verified.</small></div><div><strong>Identity / INE</strong><span className="status status--missing">Missing</span><small>Must be checked before any real disbursement.</small></div></div>
            </>}
            {step === "decision" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Explainable decision</span><h3>Committee review required.</h3><p>Olin organizes evidence; the originating institution keeps the official decision.</p></div>
              <div className="pilot-score-grid"><div className="pilot-score-card pilot-score-card--hero"><span>Olin score</span><strong>68.4</strong><small>CI 57.1–75.6 · coverage 60%</small></div><div className="pilot-score-card"><span>Route</span><strong>Tier 7</strong><small>C2 · D2 · S2</small></div><div className="pilot-score-card"><span>Suggested action</span><strong>Committee</strong><small>Review missing identity and bank evidence.</small></div></div>
              <div className="pilot-reasons"><strong>Why this route?</strong><ul><li>Cash-flow capacity is adequate but based on synthetic evidence.</li><li>No verified Círculo consent or INE record is attached.</li><li>Olin cannot authorize a disbursement from this shadow case.</li></ul></div>
            </>}
            {step === "outcome" && <>
              <div className="pilot-workspace__heading"><span className="pilot-workspace__kicker">Partner comparison</span><h3>Turn the decision into evidence.</h3><p>Record the partner's independent decision so the pilot produces usable learning data.</p></div>
              <div className="pilot-outcome"><div><span>Olin recommendation</span><strong>Committee</strong></div><div><span>Partner decision</span><div className="pilot-choice-row"><button type="button" className={partnerDecision === "approved" ? "is-selected" : ""} onClick={() => setPartnerDecision("approved")}>Approve</button><button type="button" className={partnerDecision === "declined" ? "is-selected" : ""} onClick={() => setPartnerDecision("declined")}>Decline</button></div></div><div><span>Agreement</span><strong>{partnerDecision === "pending" ? "Pending partner input" : partnerDecision === "declined" ? "Recorded · different route" : "Recorded · aligned route"}</strong></div></div>
            </>}
          </section>
        </AnimatePresence>
        <div className="pilot-workspace__footer"><span>{completed ? "Case complete · partner outcome recorded in demo" : submitted ? "Case saved to the pilot ledger" : "Interactive demonstration"}</span><button type="button" className="button button--signal" disabled={completed || (step === "intake" && !consent)} onClick={advance}>{completed ? "Completed ✓" : step === "outcome" ? "Case complete" : step === "intake" ? "Create shadow case" : "Continue"}<span aria-hidden="true">{completed ? "" : "→"}</span></button></div>
      </div>
    </MotionConfig>
  );
}
