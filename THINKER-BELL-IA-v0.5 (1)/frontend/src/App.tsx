import { FormEvent, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { api, post, setUnauthorizedHandler } from "./api";
import type { components } from "./api-types";

type S = components["schemas"];
type User = S["UserOut"]; type Patient = S["PatientOut"]; type Evaluation = S["EvaluationOut"];

function useLoad<T>(path: string) {
  const [data, setData] = useState<T | null>(null); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const ctl = useRef<AbortController | null>(null);
  const reload = useCallback(() => {
    ctl.current?.abort();                                    // la petición anterior ya no importa
    const ac = new AbortController(); ctl.current = ac; setLoading(true); setError("");
    api<T>(path, { signal: ac.signal })
      .then((d) => { if (!ac.signal.aborted) setData(d); })
      .catch((e) => { if (!ac.signal.aborted && (e as Error).name !== "AbortError") setError((e as Error).message); })
      .finally(() => { if (!ac.signal.aborted) setLoading(false); });
  }, [path]);
  useEffect(() => { reload(); return () => ctl.current?.abort(); }, [reload]);
  return { data, error, loading, reload };
}

function useDebounced<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

function State({ loading, error, empty, children }: { loading: boolean; error: string; empty?: boolean; children: ReactNode }) {
  if (loading) return <p className="empty" role="status">Cargando…</p>;
  if (error) return <p className="msg err" role="alert">{error}</p>;
  if (empty) return <p className="empty">Aún no hay registros. Crea el primero desde su sección.</p>;
  return <>{children}</>;
}
const Risk = ({ r }: { r: string }) => <span className={`badge ${r}`}>{r}</span>;
const statusText = (s: string) => (s === "PENDIENTE_DE_VALIDACION_CLINICA" ? "pendiente de validación clínica" : s);
const fmt = (s: string) => new Date(s).toLocaleString("es-CO", { timeZone: "America/Bogota" });

function Login({ notice, onLogin }: { notice: string; onLogin: (u: User) => void }) {
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const f = new FormData(e.currentTarget); setBusy(true); setErr("");
    try { onLogin(await post<User>("/auth/login", { username: f.get("u"), password: f.get("p") })); } catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  return <div className="login card"><h1>Thinker Bell</h1><p style={{ color: "var(--mute)" }}>Apoyo a la evaluación NEWS2. Entorno de demostración con datos sintéticos.</p>
    {notice && <p className="msg err" role="status">{notice}</p>}
    <form onSubmit={submit} className="grid"><label>Usuario<input name="u" autoComplete="username" required /></label>
      <label>Contraseña<input name="p" type="password" autoComplete="current-password" required /></label>
      {err && <p className="msg err" role="alert">{err}</p>}<button className="primary" disabled={busy}>{busy ? "Entrando…" : "Iniciar sesión"}</button></form></div>;
}

function ChangePassword({ forced, onDone }: { forced: boolean; onDone: (u: User) => void }) {
  const [err, setErr] = useState(""); const [busy, setBusy] = useState(false); const [ok, setOk] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); setErr(""); setOk(false);
    if (f.get("n") !== f.get("n2")) { setErr("La confirmación no coincide."); return; }
    setBusy(true);
    try { const u = await post<User>("/auth/change-password", { current_password: f.get("c"), new_password: f.get("n") }); form.reset(); setOk(true); onDone(u); }
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  return <div className={forced ? "login card" : "card"}><h2>{forced ? "Debes cambiar tu contraseña para continuar" : "Cambiar contraseña"}</h2>
    <form onSubmit={submit} className="grid">
      <label>Contraseña actual<input name="c" type="password" autoComplete="current-password" required /></label>
      <label>Nueva contraseña (mín. 12 caracteres)<input name="n" type="password" autoComplete="new-password" minLength={12} maxLength={128} required /></label>
      <label>Repite la nueva contraseña<input name="n2" type="password" autoComplete="new-password" minLength={12} maxLength={128} required /></label>
      {err && <p className="msg err" role="alert">{err}</p>}
      {ok && <p className="msg ok" role="status">Contraseña actualizada. Se cerraron tus otras sesiones.</p>}
      <button className="primary" disabled={busy}>{busy ? "Guardando…" : "Guardar contraseña"}</button></form></div>;
}

function Dashboard() {
  const { data, error, loading } = useLoad<S["DashboardOut"]>("/dashboard/summary");
  const dist = Object.entries(data?.risk_distribution ?? {}); const max = Math.max(1, ...dist.map(([, n]) => n));
  const days = data?.per_day ?? []; const dmax = Math.max(1, ...days.map((d) => d.count));
  return <State loading={loading} error={error}>{data && <div className="grid">
    <div className="grid kpis"><div className="card kpi"><span>Evaluaciones registradas</span><b>{data.evaluations}</b></div>
      <div className="card kpi"><span>Pacientes registrados</span><b>{data.patients}</b></div>
      <div className="card kpi danger"><span>Evaluaciones con riesgo alto</span><b>{data.risk_distribution["Alto"] ?? 0}</b></div></div>
    {data.evaluations === 0 ? <p className="card empty">Sin evaluaciones todavía. Registra un paciente y realiza una evaluación para ver aquí los indicadores.</p> :
    <><div className="grid two"><div className="card"><h2>Distribución por categoría de riesgo</h2>
      {dist.map(([k, n]) => <div className="bar" key={k}><span>{k}</span><i className={k} style={{ width: `${(n / max) * 70}%` }} /><span>{n}</span></div>)}</div>
      <div className="card"><h2>Evaluaciones por día (últimos 7 con actividad)</h2><div className="cols">{days.map((d) => <div key={d.day}><i style={{ height: `${(d.count / dmax) * 90}px` }} />{d.count}<br />{d.day.slice(5)}</div>)}</div></div></div>
    <div className="card"><h2>Actividad reciente</h2><EvalTable rows={data.recent} /></div></>}</div>}</State>;
}

function EvalTable({ rows }: { rows: Evaluation[] }) {
  return <div className="wrap" tabIndex={0} role="region" aria-label="Tabla de datos"><table><caption>Evaluaciones más recientes</caption><thead><tr><th scope="col">Fecha</th><th>Paciente</th><th>Puntaje</th><th>Riesgo</th><th>Versión de reglas</th></tr></thead>
    <tbody>{rows.map((r) => <tr key={r.evaluation_id}><td>{fmt(r.timestamp)}</td><td>{r.patient_id}</td><td>{r.total_score}</td><td><Risk r={r.clinical_risk} /></td><td>{r.algorithm_version}</td></tr>)}</tbody></table></div>;
}

const LABELS: Record<string, string> = { respiratory_rate: "Frecuencia respiratoria", oxygen_saturation: "Saturación de O₂", supplemental_oxygen: "Oxígeno suplementario",
  systolic_bp: "Presión sistólica", heart_rate: "Frecuencia cardiaca", consciousness: "Conciencia", temperature: "Temperatura" };

function NewEvaluation() {
  const pts = useLoad<S["PatientPage"]>("/patients?limit=100"); const [res, setRes] = useState<Evaluation | null>(null); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); setBusy(true); setErr(""); setRes(null);
    const n = (k: string) => Number(f.get(k));
    // Tipado con el contrato generado: un campo con typo (p. ej. spo2_scale2) no compila.
    const body: S["EvaluateIn"] = {
      patient_id: String(f.get("patient_id")),
      pregnancy: f.get("pg") as S["EvaluateIn"]["pregnancy"],
      spinal_cord_injury: f.get("sci") === "on",
      vitals: { respiratory_rate: n("rr"), oxygen_saturation: n("spo2"), supplemental_oxygen: f.get("o2") === "on", spo2_scale_2: f.get("s2") === "on",
                systolic_bp: n("sbp"), heart_rate: n("hr"), consciousness: f.get("c") as S["VitalsIn"]["consciousness"], temperature: n("t") },
    };
    try { setRes(await post<Evaluation>("/triage/evaluate", body)); form.reset(); }   // limpiar evita arrastrar datos al siguiente paciente
    catch (x) { setErr((x as Error).message); } finally { setBusy(false); }
  }
  return <div className="grid"><State loading={pts.loading} error={pts.error} empty={pts.data?.total === 0}>
    <form className="card f" onSubmit={submit}>
      <label>Paciente<select name="patient_id" required defaultValue="">{<option value="" disabled>Selecciona…</option>}{pts.data?.items.map((p) => <option key={p.patient_id} value={p.patient_id}>{p.patient_id} · {p.full_name}</option>)}</select></label>
      <label>Frecuencia respiratoria (rpm)<input name="rr" type="number" min={1} max={70} required /></label>
      <label>SpO₂ (%)<input name="spo2" type="number" min={50} max={100} required /></label>
      <label>Presión sistólica (mmHg)<input name="sbp" type="number" min={40} max={300} required /></label>
      <label>Frecuencia cardiaca (lpm)<input name="hr" type="number" min={20} max={250} required /></label>
      <label>Temperatura (°C)<input name="t" type="number" step="0.1" min={30} max={45} required /></label>
      <label>Conciencia<select name="c" defaultValue="A"><option value="A">Alerta</option><option value="C">Confusión nueva</option><option value="V">Responde a voz</option><option value="P">Responde a dolor</option><option value="U">No responde</option></select></label>
      <label>Embarazo<select name="pg" required defaultValue=""><option value="" disabled>Selecciona…</option><option value="no">No</option><option value="yes">Sí</option><option value="unknown">No determinado</option></select></label>
      <label className="chk"><input name="sci" type="checkbox" />Lesión medular</label>
      <label className="chk"><input name="o2" type="checkbox" />Recibe oxígeno suplementario</label>
      <label className="chk"><input name="s2" type="checkbox" />Escala 2 de SpO₂ (indicada por profesional)</label>
      <div><button className="primary" disabled={busy}>{busy ? "Calculando…" : "Calcular y guardar"}</button></div></form></State>
    {err && <p className="msg err" role="alert">{err}</p>}
    {res && <div className="card" role="status"><h2>Resultado: {res.total_score} puntos <Risk r={res.clinical_risk} /></h2>
      {res.alerts.map((a) => <p key={a.code} className={`msg alert ${a.severity}`} role="alert">{a.text}</p>)}
      <p>{res.recommended_response}</p>
      <div className="wrap" tabIndex={0} role="region" aria-label="Tabla de datos"><table><tbody>{Object.entries(res.parameter_scores).map(([k, v]) => <tr key={k}><td>{LABELS[k] ?? k}</td><td>{v}</td></tr>)}</tbody></table></div>
      <p className="msg ok">Guardado con las reglas {res.algorithm_version} ({statusText(res.rules_status)}). No es un diagnóstico.</p></div>}</div>;
}

function Patients({ user }: { user: User }) {
  const [q, setQ] = useState(""); const dq = useDebounced(q, 250);   // cada GET /patients genera una fila de auditoría de acceso: sin debounce serían una por tecla
  const { data, error, loading, reload } = useLoad<S["PatientPage"]>(`/patients?limit=50&q=${encodeURIComponent(dq)}`);
  const [err, setErr] = useState(""); const can = user.role !== "auditor";
  const [target, setTarget] = useState(""); const [rv, setRv] = useState<Patient | null>(null); const [rvErr, setRvErr] = useState("");
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); setErr("");
    const bd = String(f.get("bd") ?? ""), age = String(f.get("a") ?? "");
    const body: S["PatientIn"] = { patient_id: String(f.get("id")), full_name: String(f.get("n")), age: age ? Number(age) : null,
                                    birth_date: bd || null, gender: f.get("g") as S["PatientIn"]["gender"] };
    try { await post("/patients", body); form.reset(); reload(); } catch (x) { setErr((x as Error).message); }
  }
  async function reveal(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); const form = e.currentTarget; const f = new FormData(form); setRvErr(""); setRv(null);
    try { setRv(await post<Patient>(`/patients/${encodeURIComponent(target)}/break-glass`, { reason: f.get("r") })); form.reset(); }
    catch (x) { setRvErr((x as Error).message); }
  }
  return <div className="grid">{can && <form className="card f" onSubmit={add}><label>Identificador interno<input name="id" pattern="[A-Za-z0-9_-]{1,64}" required placeholder="SYN-001" /></label>
    <label>Nombre (sintético)<input name="n" required maxLength={200} /></label>
    <label>Fecha de nacimiento (opcional)<input name="bd" type="date" /></label>
    <label>Edad (si no hay fecha)<input name="a" type="number" min={0} max={120} /></label>
    <label>Sexo<select name="g" defaultValue="unknown"><option value="unknown">No especificado</option><option value="female">Femenino</option><option value="male">Masculino</option><option value="other">Otro</option></select></label>
    <div><button className="primary">Registrar paciente</button></div>{err && <p className="msg err" role="alert">{err}</p>}</form>}
    <div className="card"><label>Buscar por identificador<input value={q} maxLength={64} onChange={(e) => setQ(e.target.value)} placeholder="Comienza con el identificador" /></label>
      <State loading={loading} error={error} empty={data?.total === 0 && !dq}>{data?.total === 0 ? <p className="empty">Sin coincidencias.</p> :
      <div className="wrap" tabIndex={0} role="region" aria-label="Tabla de datos"><table><thead><tr><th>ID</th><th>Nombre</th><th>Edad</th><th>Sexo</th>{user.role === "admin" && <th>Acción</th>}</tr></thead>
        <tbody>{data?.items.map((p) => <tr key={p.patient_id}><td>{p.patient_id}</td><td>{p.full_name ?? "Oculto por rol"}</td><td>{p.age ?? "—"}</td><td>{p.gender}</td>
          {user.role === "admin" && <td><button className="ghost" onClick={() => { setTarget(p.patient_id); setRv(null); setRvErr(""); }}>Acceso de emergencia</button></td>}</tr>)}</tbody></table></div>}</State></div>
    {user.role === "admin" && target && <form className="card f" onSubmit={reveal}>
      <p className="banner">Acceso de emergencia a {target}: queda registrado de forma permanente con tu usuario y el motivo. No escribas datos del paciente en el motivo.</p>
      <label>Motivo (15 a 200 caracteres)<input name="r" minLength={15} maxLength={200} required /></label>
      <div><button className="primary">Revelar datos</button> <button type="button" className="ghost" onClick={() => { setTarget(""); setRv(null); }}>Cancelar</button></div>
      {rvErr && <p className="msg err" role="alert">{rvErr}</p>}
      {rv && <p className="msg ok" role="status">{rv.full_name} · {rv.age ?? "—"} años · nacimiento {rv.birth_date ?? "—"}</p>}</form>}</div>;
}

function History() {
  const [risk, setRisk] = useState(""); const [page, setPage] = useState(0); const L = 15;
  const { data, error, loading } = useLoad<S["EvaluationPage"]>(`/triage/evaluations?limit=${L}&offset=${page * L}${risk ? `&risk=${risk}` : ""}`);
  return <div className="card"><label>Categoría de riesgo<select value={risk} onChange={(e) => { setRisk(e.target.value); setPage(0); }}><option value="">Todas</option>{["Bajo", "Bajo-Medio", "Medio", "Alto"].map((r) => <option key={r}>{r}</option>)}</select></label>
    <State loading={loading} error={error} empty={data?.total === 0}>{data && <><EvalTable rows={data.items} />
      <p>{data.total} evaluaciones · <button className="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Anterior</button> <button className="ghost" disabled={(page + 1) * L >= data.total} onClick={() => setPage(page + 1)}>Siguiente</button></p></>}</State></div>;
}

function Motor() {
  const { data, error, loading } = useLoad<S["News2InfoOut"]>("/news2/info");
  return <State loading={loading} error={error}>{data && <div className="card"><h2>Motor NEWS2</h2>
    <p className="banner">Estado: {statusText(data.rules_status)}. {data.notice}</p>
    <p>Versión de reglas implementada: <b>{data.algorithm_version}</b></p><p>Fuente de referencia: {data.source}</p>
    <p>Las reglas residen únicamente en el servidor. Cada evaluación guarda la versión usada y los datos de entrada para poder reproducirla.</p></div>}</State>;
}

function Docs() {
  return <div className="card"><h2>Documentación</h2><p>Thinker Bell calcula el puntaje NEWS2 a partir de signos vitales y conserva el historial de evaluaciones y su auditoría.</p>
    <h2>Alcance y limitaciones</h2><p>Entorno de demostración con datos sintéticos. El motor NEWS2 está pendiente de validación clínica; no es un diagnóstico ni un producto sanitario autorizado, y no sustituye el juicio profesional ni el protocolo institucional. No hay modelos de IA ni integraciones externas activas.</p>
    <h2>Guía de uso</h2><p>1) Registra un paciente. 2) Crea una evaluación con sus signos vitales (rol clínico). 3) Consulta el panel y el historial. Los auditores tienen acceso de solo lectura.</p>
    <p>Detalles técnicos y de seguridad: README.md y docs/ en el repositorio.</p></div>;
}

const NAV = [["dash", "Panel de control"], ["eval", "Nueva evaluación"], ["pts", "Pacientes"], ["hist", "Historial"], ["news2", "Motor NEWS2"], ["docs", "Documentación"], ["acct", "Mi cuenta"]] as const;

export default function App() {
  const [user, setUser] = useState<User | null>(null); const [ready, setReady] = useState(false); const [view, setView] = useState<string>("dash"); const [menu, setMenu] = useState(false);
  const [notice, setNotice] = useState("");
  useEffect(() => { api<User>("/auth/me").then(setUser).catch(() => setUser(null)).finally(() => setReady(true)); }, []);
  useEffect(() => {   // sesión caducada o revocada: volver al login y descartar cualquier dato en pantalla (incluido el de acceso de emergencia)
    setUnauthorizedHandler(() => { setUser(null); setView("dash"); setMenu(false); setNotice("Tu sesión expiró o se cerró en otro lugar. Inicia sesión de nuevo."); });
    return () => setUnauthorizedHandler(() => {});
  }, []);
  if (!ready) return <p className="empty" role="status">Cargando…</p>;
  if (!user) return <Login notice={notice} onLogin={(u) => { setNotice(""); setUser(u); }} />;
  const logout = () => post("/auth/logout", {}).finally(() => { setNotice(""); setView("dash"); setUser(null); });
  if (user.must_change_password) return <><ChangePassword forced onDone={setUser} />
    <p style={{ textAlign: "center" }}><button className="ghost" onClick={logout}>Cerrar sesión</button></p></>;
  const nav = NAV.filter(([k]) => k !== "eval" || user.role === "clinician"); const cur = nav.some(([k]) => k === view) ? view : "dash";
  return <div className="shell"><div className="mobilebar"><b>Thinker Bell</b><button className="ghost" aria-expanded={menu} aria-controls="nav" onClick={() => setMenu(!menu)}>{menu ? "Cerrar menú" : "Menú"}</button></div>
    <nav id="nav" className={menu ? "open" : ""} aria-label="Principal"><div className="brand">Thinker Bell</div>
    {nav.map(([k, l]) => <button key={k} aria-current={cur === k ? "page" : undefined} onClick={() => { setView(k); setMenu(false); }}>{l}</button>)}
    <div className="who">{user.username} · {user.role}<br /><button className="ghost" onClick={logout}>Cerrar sesión</button></div></nav>
    <main><header className="top"><h1>{nav.find(([k]) => k === cur)![1]}</h1></header>
      <p className="banner">Demostración con datos sintéticos · Reglas NEWS2 pendientes de validación clínica · No es un diagnóstico.</p>
      {cur === "dash" && <Dashboard />}{cur === "eval" && <NewEvaluation />}{cur === "pts" && <Patients user={user} />}{cur === "hist" && <History />}{cur === "news2" && <Motor />}{cur === "docs" && <Docs />}{cur === "acct" && <ChangePassword forced={false} onDone={setUser} />}</main></div>;
}
