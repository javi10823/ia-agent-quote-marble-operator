/**
 * E2E del Route Handler `/api/session` · Sprint 4 ssr-auth.
 *
 * Cubre:
 * - POST con body válido setea cookie httpOnly (200 + Set-Cookie).
 * - POST sin body / sin token → 400.
 * - DELETE limpia la cookie (200 + Set-Cookie con maxAge=0).
 * - La cookie tiene flags correctas (httpOnly, SameSite=lax, path=/).
 *
 * Fix-up #1 PR #469: status 200 + JSON body (en vez de 204 null body) por
 * el issue de Vercel cold start que devolvía 503. El comportamiento
 * funcional (cookie seteada / borrada) no cambia.
 *
 * NO testea que el SSR del [id]/layout use el header — eso requiere
 * backend real Railway con sesión válida (test manual + visual local).
 */
import { expect, test } from "@playwright/test";

test("POST /api/session con token válido setea cookie 200", async ({ request }) => {
  const res = await request.post("/api/session", {
    data: { token: "test-jwt-value.xxx.yyy" },
  });
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ ok: true });
  const setCookie = res.headers()["set-cookie"];
  expect(setCookie).toBeTruthy();
  expect(setCookie).toContain("vercel_session_token=test-jwt-value.xxx.yyy");
  expect(setCookie).toContain("HttpOnly");
  expect(setCookie).toContain("SameSite=lax");
  expect(setCookie).toContain("Path=/");
});

test("POST /api/session sin body → 400", async ({ request }) => {
  const res = await request.post("/api/session", { data: "" });
  expect(res.status()).toBe(400);
});

test("POST /api/session con token vacío → 400", async ({ request }) => {
  const res = await request.post("/api/session", { data: { token: "   " } });
  expect(res.status()).toBe(400);
});

test("DELETE /api/session limpia la cookie con 200 (no 503 ni 204)", async ({ request }) => {
  // Fix-up #1 PR #469 · CFC detectó 503 en preview real con la versión 204
  // null body. Ahora 200 + JSON body evita el quirk del Vercel cold start.
  const res = await request.delete("/api/session");
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ ok: true });
  const setCookie = res.headers()["set-cookie"];
  expect(setCookie).toBeTruthy();
  expect(setCookie).toContain("vercel_session_token=");
  expect(setCookie).toContain("Max-Age=0");
  expect(setCookie).toContain("HttpOnly");
});

test("DELETE /api/session después de POST elimina efectivamente la cookie del browser", async ({
  request,
}) => {
  // Flujo completo end-to-end con el cookie jar del request context.
  const post = await request.post("/api/session", { data: { token: "abc.def.ghi" } });
  expect(post.status()).toBe(200);
  const del = await request.delete("/api/session");
  expect(del.status()).toBe(200);
  // El siguiente fetch al endpoint (cualquiera same-origin) no debería
  // llevar la cookie · el Max-Age=0 la invalidó.
  const setCookieDel = del.headers()["set-cookie"] ?? "";
  expect(setCookieDel).toMatch(/vercel_session_token=;.*Max-Age=0/);
});
