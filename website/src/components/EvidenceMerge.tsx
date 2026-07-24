import { useRef } from "react";
import { LazyMotion, MotionConfig, domAnimation, m, useInView, useReducedMotion } from "motion/react";

const inputs = [
  { code: "C1", label: "Círculo", note: "consentimiento registrado" },
  { code: "2.2×", label: "Capacidad", note: "fuente identificada" },
  { code: "82", label: "Operación", note: "señal observada" }
];

export default function EvidenceMerge() {
  const ref = useRef<HTMLDivElement>(null);
  const visible = useInView(ref, { once: true, amount: .42 });
  const reduced = useReducedMotion();

  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation} strict>
        <div className="merge-visual" ref={ref} aria-label="Tres fuentes convergen en un expediente auditable">
          <div className="merge-visual__inputs">
            {inputs.map((input, index) => (
              <m.div
                className="merge-input"
                key={input.label}
                initial={false}
                animate={visible && !reduced ? { opacity: [.58, 1], x: [-12, 0], scale: [.98, 1] } : { opacity: 1, x: 0, scale: 1 }}
                transition={{ duration: .38, delay: index * .08, ease: [0.16, 1, 0.3, 1] }}
              >
                <span>{input.code}</span>
                <div><strong>{input.label}</strong><small>{input.note}</small></div>
              </m.div>
            ))}
          </div>

          <svg className="merge-visual__lines" viewBox="0 0 300 220" preserveAspectRatio="none" aria-hidden="true">
            <path d="M0 36 C120 36 116 110 300 110" />
            <path d="M0 110 H300" />
            <path d="M0 184 C120 184 116 110 300 110" />
            {!reduced && ["M0 36 C120 36 116 110 300 110", "M0 110 H300", "M0 184 C120 184 116 110 300 110"].map((path, index) => (
              <m.path key={path} d={path} initial={{ pathLength: 0, opacity: 0 }} animate={visible ? { pathLength: 1, opacity: 1 } : { pathLength: 0, opacity: 0 }} transition={{ duration: .65, delay: .16 + index * .1, ease: [0.22, 1, 0.36, 1] }} />
            ))}
          </svg>

          <m.div
            className="merge-output"
            initial={false}
            animate={visible && !reduced ? { opacity: [.7, 1], x: [12, 0], scale: [.96, 1] } : { opacity: 1, x: 0, scale: 1 }}
            transition={{ duration: .36, delay: .76, ease: [0.16, 1, 0.3, 1] }}
          >
            <span>OL</span>
            <div><small>Expediente Olin</small><strong>Una ruta auditable</strong></div>
            <b aria-hidden="true">→</b>
          </m.div>
        </div>
      </LazyMotion>
    </MotionConfig>
  );
}
