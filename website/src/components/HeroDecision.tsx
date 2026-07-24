import { Fragment, useEffect, useState } from "react";
import { LazyMotion, MotionConfig, domAnimation, m, useReducedMotion } from "motion/react";

const sources = [
  { value: "C1", note: "Círculo ≥ 670" },
  { value: "2,7×", note: "Capacidad estimada" },
  { value: "81", note: "Indicador interno" }
];

const paths = [
  "M72 40 C170 40 148 120 248 120",
  "M72 120 H248",
  "M72 200 C170 200 148 120 248 120"
];

const enterEase = [0.16, 1, 0.3, 1] as const;

const pathVariants = {
  idle: { pathLength: 0, opacity: 0 },
  ready: (delay: number) => ({
    pathLength: 1,
    opacity: 1,
    transition: { duration: 0.58, delay, ease: enterEase }
  })
};

export default function HeroDecision() {
  const [ready, setReady] = useState(false);
  const [run, setRun] = useState(0);
  const reduced = useReducedMotion();

  useEffect(() => {
    setReady(false);
    const frame = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(frame);
  }, [run]);

  const replay = () => setRun((current) => current + 1);
  const finalState = ready || reduced;

  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation} strict>
        <div className="decision-stage" aria-label="Caso sintético que conecta tres dimensiones con una recomendación">
          <div className="decision-stage__top">
            <span>OL / EXPEDIENTE / 0142</span>
            <div className="decision-stage__top-actions">
              <span className="decision-stage__live">Caso sintético</span>
              {!reduced && (
                <button className="decision-stage__replay" type="button" onClick={replay} aria-label="Repetir la animación del flujo">
                  <m.svg viewBox="0 0 24 24" aria-hidden="true" animate={{ rotate: run * 360 }} transition={{ duration: .38, ease: enterEase }}>
                    <path d="M20 11a8 8 0 1 0-2.34 5.66M20 4v7h-7" />
                  </m.svg>
                  <span>Repetir</span>
                </button>
              )}
            </div>
          </div>

          <Fragment key={run}>
            <m.div
              className="decision-stage__merchant"
              initial={reduced ? false : { opacity: 0, y: 12 }}
              animate={finalState ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
              transition={{ duration: .36, delay: .12, ease: enterEase }}
            >
              <span className="decision-stage__merchant-avatar">SL</span>
              <div>
                <strong>Tienda de abarrotes San Luis</strong>
                <small>Iztapalapa · solicitud de MXN 25,000</small>
              </div>
              <span className="tag tag--dark">3 fuentes</span>
            </m.div>

            <div className="decision-stage__body">
              <div className="decision-flow">
                {sources.map((source, index) => (
                  <m.div
                    className="decision-flow__source"
                    key={source.value}
                    initial={reduced ? false : { opacity: 0, x: -14, scale: .97 }}
                    animate={finalState ? { opacity: 1, x: 0, scale: 1 } : { opacity: 0, x: -14, scale: .97 }}
                    transition={{ duration: .34, delay: .28 + index * .09, ease: enterEase }}
                  >
                    <strong>{source.value}</strong><small>{source.note}</small>
                  </m.div>
                ))}

                <m.div
                  className="decision-flow__core"
                  initial={reduced ? false : { opacity: 0, scale: .82 }}
                  animate={finalState ? { opacity: 1, scale: 1 } : { opacity: 0, scale: .82 }}
                  transition={{ type: "spring", stiffness: 240, damping: 19, delay: .88 }}
                >
                  <strong>01</strong><small>Ruta</small>
                </m.div>

                <svg className="decision-flow__svg" viewBox="0 0 320 240" preserveAspectRatio="none" aria-hidden="true">
                  {paths.map((path) => <path d={path} key={`base-${path}`} />)}
                  {!reduced && paths.map((path, index) => (
                    <m.path
                      d={path}
                      key={path}
                      custom={.56 + index * .13}
                      variants={pathVariants}
                      initial="idle"
                      animate={ready ? "ready" : "idle"}
                      stroke="var(--signal)"
                      strokeWidth="2.5"
                      fill="none"
                    />
                  ))}
                </svg>
              </div>

              <m.div
                className="decision-result"
                initial={reduced ? false : { opacity: 0, x: 18, scale: .97 }}
                animate={finalState ? { opacity: 1, x: 0, scale: 1 } : { opacity: 0, x: 18, scale: .97 }}
                transition={{ duration: .42, delay: 1.08, ease: enterEase }}
              >
                <small>Recomendación del motor</small>
                <m.div
                  className="decision-result__tier"
                  initial={false}
                  animate={ready && !reduced ? { scale: [1, 1.1, 1] } : { scale: 1 }}
                  transition={{ duration: .42, delay: 1.32, ease: enterEase }}
                >R1</m.div>
                <div>
                  <strong>RUTA<br />FAVORABLE</strong>
                  <p>La institución revisa las fuentes, el monto y conserva la decisión final.</p>
                </div>
              </m.div>
            </div>
          </Fragment>
        </div>
      </LazyMotion>
    </MotionConfig>
  );
}
