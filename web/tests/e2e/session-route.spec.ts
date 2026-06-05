/**
 * E2E del Route Handler `/api/session` · Sprint 4 ssr-auth.
 *
 * Cubre:
 * - POST con body válido setea cookie httpOnly (204 + Set-Cookie).
 * - POST sin body / sin token → 400.
 * - DELETE limpia la cookie (204 + Set-Cookie con maxAge=0).
 * - La cookie tiene flags correctas (httpOnly, SameSite=lax, path=/).
 *
 * NO testea que el SSR del [id]/layout use el header — eso requiere
 * backend real Railway con sesión válida (test manual + visual local).
 */
import { expect, test } from "@playwright/test";

test("POST /api/session con token válido setea cookie 204", async ({ request }) => {
  const res = await request.post("/api/session", {
    data: { token: "test-jwt-value.xxx.yyy" },
  });
  expect(res.status()).toBe(204);
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

test("DELETE /api/session limpia la cookie", async ({ request }) => {
  const res = await request.delete("/api/session");
  expect(res.status()).toBe(204);
  const setCookie = res.headers()["set-cookie"];
  expect(setCookie).toBeTruthy();
  expect(setCookie).toContain("vercel_session_token=");
  expect(setCookie).toContain("Max-Age=0");
  expect(setCookie).toContain("HttpOnly");
});
