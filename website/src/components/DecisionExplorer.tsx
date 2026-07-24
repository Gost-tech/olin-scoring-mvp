import { useId, useRef, useState } from "react";
import { AnimatePresence, LazyMotion, MotionConfig, domMax, m, useReducedMotion } from "motion/react";

type Profile = {
  id: string;
  short: string;
  label: string;
  application: string;
  merchant: string;
  amount: string;
  tenure: string;
  evidence: string;
  bands: Array<{ label: string; value: string; detail: string }>;
  tier: string;
  decision: string;
  reason: string;
};

const profiles: Profile[] = [
  {
    id: "solid",
    short: "01",
    label: "Abarrotes",
    application: "OL-0142",
    merchant: "Tienda de abarrotes San Luis",
    amount: "MXN 25,000",
    tenure: "9 años",
    evidence: "Banco + compras",
    bands: [
      { label: "Historial crediticio", value: "C1", detail: "puntaje ≥ 670" },
      { label: "Capacidad estimada", value: "D1", detail: "2,7× la cuota" },
      { label: "Señales operativas", value: "S1", detail: "81 / 100" }
    ],
    tier: "Ruta 1",
    decision: "Recomendación favorable",
    reason: "La política ilustrativa ubica el caso en su ruta favorable. La institución todavía revisa las fuentes, el monto y la decisión final."
  },
  {
    id: "thin",
    short: "02",
    label: "Taquería",
    application: "OL-0191",
    merchant: "Taquería La Aurora",
    amount: "MXN 32,000",
    tenure: "5 años",
    evidence: "Banco + TPV",
    bands: [
      { label: "Historial crediticio", value: "C3", detail: "sin expediente" },
      { label: "Capacidad estimada", value: "D2", detail: "1,9× la cuota" },
      { label: "Señales operativas", value: "S1", detail: "77 / 100" }
    ],
    tier: "Ruta 11",
    decision: "Comité",
    reason: "La matriz real asigna C3 · D2 · S1 a la Ruta 11. El expediente sin historial requiere revisión de fuentes, supuestos y estacionalidad."
  },
  {
    id: "stress",
    short: "03",
    label: "Papelería",
    application: "OL-0208",
    merchant: "Papelería El Puente",
    amount: "MXN 48,000",
    tenure: "3 años",
    evidence: "Banco + inventario",
    bands: [
      { label: "Historial crediticio", value: "C2", detail: "600–669" },
      { label: "Capacidad estimada", value: "D3", detail: "1,2× la cuota" },
      { label: "Señales operativas", value: "S2", detail: "58 / 100" }
    ],
    tier: "Ruta 13",
    decision: "No recomendada",
    reason: "La cobertura de deuda inferior a 1,5× activa la Ruta 13 en la política actual. El caso no avanza con este monto y estos supuestos."
  }
];

export default function DecisionExplorer() {
  const [activeIndex, setActiveIndex] = useState(0);
  const reduced = useReducedMotion();
  const groupId = useId();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const active = profiles[activeIndex];

  const select = (index: number, moveFocus = false) => {
    const nextIndex = (index + profiles.length) % profiles.length;
    setActiveIndex(nextIndex);
    if (moveFocus) tabRefs.current[nextIndex]?.focus();
  };
  const onKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") { event.preventDefault(); select(index + 1, true); }
    if (event.key === "ArrowLeft" || event.key === "ArrowUp") { event.preventDefault(); select(index - 1, true); }
    if (event.key === "Home") { event.preventDefault(); select(0, true); }
    if (event.key === "End") { event.preventDefault(); select(profiles.length - 1, true); }
  };

  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domMax} strict>
        <div className="decision-explorer">
          <div className="explorer-tabs" role="tablist" aria-label="Perfiles ilustrativos">
            {profiles.map((profile, index) => (
              <button
                key={profile.id}
                ref={(node) => { tabRefs.current[index] = node; }}
                id={`${groupId}-tab-${profile.id}`}
                className="explorer-tab"
                type="button"
                role="tab"
                aria-selected={activeIndex === index}
                aria-controls={`${groupId}-panel`}
                tabIndex={activeIndex === index ? 0 : -1}
                onClick={() => select(index)}
                onKeyDown={(event) => onKeyDown(event, index)}
              >
                <span>{profile.short}</span>{profile.label}
                {activeIndex === index && (reduced
                  ? <i className="explorer-tab__indicator" />
                  : <m.i className="explorer-tab__indicator" layoutId={`${groupId}-active-tab`} />)}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait" initial={false}>
            <m.div
              key={active.id}
              id={`${groupId}-panel`}
              className="explorer-panel"
              role="tabpanel"
              tabIndex={0}
              aria-labelledby={`${groupId}-tab-${active.id}`}
              initial={reduced ? false : { opacity: 0, y: 12, scale: .995 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduced ? undefined : { opacity: 0, y: -6, transition: { duration: .16, ease: [.4, 0, 1, 1] } }}
              transition={{ duration: reduced ? 0 : 0.28, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="explorer-profile">
                <small>Expediente {active.application}</small>
                <h3>{active.merchant}</h3>
                <dl className="profile-facts">
                  <div><dt>Solicita</dt><dd>{active.amount}</dd></div>
                  <div><dt>Antigüedad</dt><dd>{active.tenure}</dd></div>
                  <div><dt>Señales</dt><dd>{active.evidence}</dd></div>
                </dl>
              </div>

              <div className="explorer-dimensions">
                {active.bands.map((band) => (
                  <div className="dimension-card" key={band.label}>
                    <div className="dimension-card__top"><span>{band.label}</span><span>dato sintético</span></div>
                    <strong>{band.value}</strong>
                    <p>{band.detail}</p>
                  </div>
                ))}
              </div>

              <div className="explorer-result" aria-live="polite">
                <small>Ruta del motor</small>
                <div className="explorer-result__tier">{active.tier}</div>
                <h3>{active.decision}</h3>
                <p>{active.reason}</p>
              </div>
            </m.div>
          </AnimatePresence>
        </div>
      </LazyMotion>
    </MotionConfig>
  );
}
