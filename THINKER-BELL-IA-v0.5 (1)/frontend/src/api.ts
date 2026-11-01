export class ApiError extends Error { constructor(public status: number, m: string) { super(m); this.name = "ApiError"; } }

let onUnauthorized: () => void = () => {};
export const setUnauthorizedHandler = (f: () => void) => { onUnauthorized = f; };

const csrf = () => typeof document === "undefined" ? "" :
  document.cookie.split("; ").find((c) => c.startsWith("tb_csrf="))?.split("=")[1] ?? "";
const NO_SESSION_EXPIRY = ["/auth/login", "/auth/me"];   // un 401 aquí es esperado: credenciales malas o "no hay sesión todavía"

// Contrato: el backend usa 401 SOLO para "sesión inválida". Cualquier otro rechazo (p. ej. contraseña actual errónea) es 403/422.
export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const unsafe = !!init?.method && init.method !== "GET";
  let r: Response;
  try {
    // headers va DESPUÉS de init: ningún llamador puede quitar el token CSRF
    r = await fetch("/api/v1" + path, { credentials: "same-origin", ...init,
      headers: { "Content-Type": "application/json", ...(unsafe ? { "X-CSRF-Token": csrf() } : {}) } });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;      // cancelación voluntaria: no es un error para el usuario
    throw new ApiError(0, "Sin conexión con el servidor. Revisa la red e inténtalo de nuevo.");
  }
  if (!r.ok) {
    let m = r.status >= 500 ? "Error del servidor. Inténtalo de nuevo."
      : r.status === 429 ? "Demasiadas solicitudes. Espera unos segundos e inténtalo de nuevo."   // límite del proxy (cuerpo HTML)
      : "Solicitud rechazada.";
    try {
      const d = (await r.json()).detail;
      m = typeof d === "string" ? d : typeof d?.message === "string" ? d.message : "Datos inválidos: revisa los campos marcados.";
    } catch { /* sin cuerpo JSON */ }
    if (r.status === 401 && !NO_SESSION_EXPIRY.includes(path)) onUnauthorized();
    throw new ApiError(r.status, m);
  }
  return (r.status === 204 ? undefined : await r.json()) as T;
}

export const post = <T = void>(p: string, b: unknown) => api<T>(p, { method: "POST", body: JSON.stringify(b) });
