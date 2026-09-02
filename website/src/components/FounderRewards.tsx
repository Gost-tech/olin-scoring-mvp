import { useMemo, useState } from "react";
import { MotionConfig, m, useReducedMotion } from "motion/react";

const rewards = [
  { step: 0, label: "Aplicar", detail: "Revisión de encaje", icon: "01" },
  { step: 1, label: "1 referido", detail: "Prioridad de respuesta", icon: "02" },
  { step: 3, label: "3 referidos", detail: "Diagnóstico ampliado", icon: "03" },
];

export default function FounderRewards() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(1);
  const current = useMemo(() => rewards[active], [active]);

  return (
    <MotionConfig reducedMotion="user">
      <section className="founder-rewards" aria-labelledby="founder-rewards-title">
        <div className="founder-rewards__copy">
          <p className="section-kicker">Círculo fundador</p>
          <h2 id="founder-rewards-title">Llega antes. <em>Ayuda a elegir.</em></h2>
          <p>Después de aplicar, comparte tu enlace con otra institución que tenga el mismo problema. Las mejores referencias reciben prioridad de revisión y un diagnóstico más profundo.</p>
          <small>No es un sorteo ni una oferta de crédito. Los beneficios dependen de encaje y revisión humana.</small>
        </div>
        <div className="founder-rewards__rail" aria-label="Progreso de referidos">
          <div className="founder-rewards__track" aria-hidden="true">
            <m.span
              className="founder-rewards__fill"
              animate={{ width: `${(current.step / 3) * 100}%` }}
              transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 28 }}
            />
            <m.button
              className="founder-rewards__handle"
              type="button"
              aria-label="Arrastra para explorar los beneficios de referidos"
              drag="x"
              dragConstraints={{ left: 0, right: 180 }}
              dragElastic={0.04}
              animate={{ left: `${(current.step / 3) * 100}%` }}
              transition={reduced ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 28 }}
              onDragEnd={(_, info) => setActive(info.offset.x > 90 ? 2 : info.offset.x > 25 ? 1 : 0)}
              whileTap={reduced ? undefined : { scale: 1.12 }}
            />
          </div>
          <div className="founder-rewards__nodes">
            {rewards.map((reward, index) => (
              <button
                className={index === active ? "founder-reward founder-reward--active" : "founder-reward"}
                key={reward.label}
                type="button"
                onClick={() => setActive(index)}
                aria-pressed={index === active}
              >
                <span className="founder-reward__dot">{reward.icon}</span>
                <strong>{reward.label}</strong>
                <small>{reward.detail}</small>
              </button>
            ))}
          </div>
          <p className="founder-rewards__status" aria-live="polite">Ahora: <strong>{current.detail}</strong></p>
        </div>
      </section>
    </MotionConfig>
  );
}
