/**
 * Unit del helper getServerToken · Sprint 4 ssr-auth.
 *
 * Cubre: cookie ausente, cookie vacía/whitespace, cookie válida, error
 * de `cookies()` fuera de Server Component context.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({
  cookies: vi.fn(),
}));

import { cookies } from "next/headers";
import { getServerToken } from "@/lib/auth-server";

const mockedCookies = vi.mocked(cookies);

afterEach(() => {
  vi.restoreAllMocks();
});

function withCookie(value: string | undefined) {
  // El `cookies()` real devuelve un ReadonlyRequestCookies. Para el test
  // mockeamos solo el método `get` que usa el helper.
  mockedCookies.mockReturnValue({
    get: () =>
      value === undefined ? undefined : ({ name: "vercel_session_token", value } as never),
  } as never);
}

describe("getServerToken", () => {
  it("devuelve null cuando no hay cookie", () => {
    withCookie(undefined);
    expect(getServerToken()).toBeNull();
  });

  it("devuelve null cuando la cookie es string vacío", () => {
    withCookie("");
    expect(getServerToken()).toBeNull();
  });

  it("devuelve null cuando la cookie es solo whitespace (trim cae a vacío)", () => {
    withCookie("   ");
    expect(getServerToken()).toBeNull();
  });

  it("devuelve el token cuando la cookie está poblada (JWT-like)", () => {
    withCookie("eyJhbGciOiJIUzI1NiJ9.payload.sig");
    expect(getServerToken()).toBe("eyJhbGciOiJIUzI1NiJ9.payload.sig");
  });

  it("trimea whitespace alrededor del token", () => {
    withCookie("   eyJabc.def.ghi   ");
    expect(getServerToken()).toBe("eyJabc.def.ghi");
  });

  it("devuelve null si cookies() lanza (llamado fuera de Server Component)", () => {
    mockedCookies.mockImplementation(() => {
      throw new Error("cookies() called outside server context");
    });
    expect(getServerToken()).toBeNull();
  });
});
