import { useMemo, useState } from "react";

type Case = { id: string; merchant: string; type: string; amount: string; route: string; score: string; coverage: string; age: string; status: string; reason: string };
const seedCases: Case[] = [
  { id: "SYN-001", merchant: "Abarrotes La Esperanza", type: "Abarrotes · Iztapalapa", amount: "MXN 20,000", route: "FAVORABLE", score: "93.6", coverage: "95%", age: "12 min", status: "Pendiente de la institución", reason: "Capacidad de pago sólida, operación estable y evidencia sintética completa." },
  { id: "SYN-002", merchant: "Taquería San Miguel", type: "Alimentos · Gustavo A. Madero", amount: "MXN 30,000", route: "COMITÉ", score: "69.2", coverage: "95%", age: "28 min", status: "Revisión requerida", reason: "El perfil es viable, pero el margen de pago, el puntaje de Círculo y una política sectorial aún no calibrada requieren revisión humana." },
  { id: "SYN-003", merchant: "Taller Mecánico La Unión", type: "Servicios · Ecatepec", amount: "MXN 25,000", route: "NO RECOMENDAR", score: "12.2", coverage: "55%", age: "1 h", status: "No recomendar", reason: "Mora activa, flujo de efectivo insuficiente y señales operativas deterioradas." },
];

const routeClass = (route: string) =>
  route === "FAVORABLE" ? "favorable" : route === "COMITÉ" ? "comite" : "no-recomendar";

export default function AnalystConsole() {
  const [selectedId, setSelectedId] = useState(seedCases[0].id);
  const [filter, setFilter] = useState("all");
  const [decision, setDecision] = useState<string | null>(null);
  const selected = useMemo(() => seedCases.find((item) => item.id === selectedId) ?? seedCases[0], [selectedId]);
  const visible = filter === "all" ? seedCases : seedCases.filter((item) => item.route.toLowerCase().includes(filter));
  return <div className="analyst-console">
    <header className="analyst-console__header"><div><span className="pilot-workspace__eyebrow">Consola Olin</span><h2>Fila de expedientes</h2></div><div className="analyst-console__header-meta"><span>COHORTE demo_sintetica_01</span><strong>3 expedientes</strong></div></header>
    <div className="analyst-console__body">
      <aside className="analyst-console__queue"><div className="queue-head"><strong>Expedientes</strong><select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filtrar expedientes"><option value="all">Todas las rutas</option><option value="comité">Revisión</option><option value="favorable">Ruta favorable</option><option value="no recomendar">No recomendar</option></select></div>{visible.map((item) => <button key={item.id} type="button" className={`queue-item ${selected.id === item.id ? "is-selected" : ""}`} onClick={() => { setSelectedId(item.id); setDecision(null); }}><span><strong>{item.merchant}</strong><small>{item.id} · {item.type}</small></span><span className={`queue-route queue-route--${routeClass(item.route)}`}>{item.route}</span><small>{item.age}</small></button>)}</aside>
      <main className="analyst-console__detail"><div className="case-detail__top"><div><span className="case-id">{selected.id} · EXPEDIENTE SOMBRA</span><h3>{selected.merchant}</h3><p>{selected.type} · monto solicitado {selected.amount}</p></div><span className="case-status">{decision ?? selected.status}</span></div><div className="case-metrics"><div><span>Puntaje Olin</span><strong>{selected.score}</strong><small>intervalo de confianza · sintético</small></div><div><span>Cobertura</span><strong>{selected.coverage}</strong><small>señales disponibles</small></div><div><span>Recomendación</span><strong>{selected.route}</strong><small>la institución conserva la decisión</small></div></div><section className="signal-table"><div className="signal-table__head"><strong>Registro de evidencia</strong><span>estado de la fuente</span></div>{[["Círculo de Crédito", "Sintético verificado"],["Flujo bancario", "Sintético verificado"],["Compras a proveedores", "Sintético verificado"],["Identidad / INE", "Sintético verificado"]].map(([label, value]) => <div className="signal-row" key={label}><strong>{label}</strong><span className="is-mock">{value}</span></div>)}</section><div className="case-reason"><strong>Razones de la recomendación</strong><p>{selected.reason}</p></div><section className="analyst-actions"><div><span>Decisión de la institución</span><small>Comparación del piloto sombra. No mueve dinero.</small></div><div className="action-buttons"><button type="button" onClick={() => setDecision("Institución: aprobado")}>Aprobar</button><button type="button" onClick={() => setDecision("Institución: rechazado")}>Rechazar</button><button type="button" onClick={() => setDecision("Evidencia adicional solicitada")}>Solicitar evidencia</button></div></section><div className="case-timeline"><strong>Bitácora de auditoría</strong><ol><li><span>09:42</span>Expediente creado con consentimiento</li><li><span>09:43</span>Evidencia evaluada y recomendación generada</li><li><span>Ahora</span>{decision ?? "Pendiente de acción del analista"}</li></ol></div></main>
    </div>
  </div>;
}
