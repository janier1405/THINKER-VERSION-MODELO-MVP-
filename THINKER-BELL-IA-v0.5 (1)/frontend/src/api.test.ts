import { afterEach, describe, expect, it, vi } from "vitest";
import { api, post, setUnauthorizedHandler } from "./api";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const stub = (impl: ReturnType<typeof vi.fn>) => vi.stubGlobal("fetch", impl);
afterEach(() => { vi.unstubAllGlobals(); setUnauthorizedHandler(() => {}); });

describe("api", () => {
  it("401 en una ruta normal avisa una vez y lanza ApiError", async () => {
    const h = vi.fn(); setUnauthorizedHandler(h);
    stub(vi.fn().mockResolvedValue(res(401, { detail: "No autenticado." })));
    await expect(api("/patients")).rejects.toMatchObject({ status: 401, message: "No autenticado." });
    expect(h).toHaveBeenCalledTimes(1);
  });
  it.each(["/auth/login", "/auth/me"])("401 en %s NO cierra la sesión", async (p) => {
    const h = vi.fn(); setUnauthorizedHandler(h);
    stub(vi.fn().mockResolvedValue(res(401, { detail: "x" })));
    await expect(post(p, {})).rejects.toMatchObject({ status: 401 });
    expect(h).not.toHaveBeenCalled();
  });
  it("403 (p. ej. contraseña actual errónea) NO cierra la sesión", async () => {
    const h = vi.fn(); setUnauthorizedHandler(h);
    stub(vi.fn().mockResolvedValue(res(403, { detail: "La contraseña actual no es correcta" })));
    await expect(post("/auth/change-password", {})).rejects.toMatchObject({ status: 403 });
    expect(h).not.toHaveBeenCalled();
  });
  it("AbortError se propaga tal cual y no es sesión caducada", async () => {
    const h = vi.fn(); setUnauthorizedHandler(h);
    stub(vi.fn().mockRejectedValue(new DOMException("cancelado", "AbortError")));
    await expect(api("/patients")).rejects.toMatchObject({ name: "AbortError" });
    expect(h).not.toHaveBeenCalled();
  });
  it("fallo de red da un mensaje claro", async () => {
    stub(vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api("/patients")).rejects.toMatchObject({ status: 0, message: expect.stringContaining("Sin conexión") });
  });
  it("429 con cuerpo HTML del proxy", async () => {
    stub(vi.fn().mockResolvedValue(new Response("<html>429</html>", { status: 429 })));
    await expect(api("/patients")).rejects.toMatchObject({ status: 429, message: expect.stringContaining("Demasiadas") });
  });
  it("detail estructurado usa message; lista de validación da mensaje genérico", async () => {
    stub(vi.fn().mockResolvedValue(res(422, { detail: { code: "X", message: "Mensaje claro" } })));
    await expect(api("/x")).rejects.toMatchObject({ message: "Mensaje claro" });
    stub(vi.fn().mockResolvedValue(res(422, { detail: [{ loc: ["body"], msg: "m" }] })));
    await expect(api("/x")).rejects.toMatchObject({ message: expect.stringContaining("Datos inválidos") });
  });
  it("CSRF solo en métodos no seguros, tomado de la cookie", async () => {
    vi.stubGlobal("document", { cookie: "a=b; tb_csrf=tok123" });
    const f = vi.fn().mockImplementation(() => Promise.resolve(res(200, {}))); stub(f);
    await api("/x"); await post("/x", {});
    expect((f.mock.calls[0][1] as RequestInit).headers).not.toHaveProperty("X-CSRF-Token");
    expect((f.mock.calls[1][1] as RequestInit).headers).toMatchObject({ "X-CSRF-Token": "tok123" });
  });
  it("204 devuelve undefined", async () => {
    stub(vi.fn().mockResolvedValue(res(204)));
    await expect(post("/auth/logout", {})).resolves.toBeUndefined();
  });
});
