const API_BASE = "";

export async function login(email: string, password: string): Promise<{ ok: boolean; email: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
    credentials: "include",
  });
  if (res.status === 401) {
    const err = await res.json();
    throw new Error(err.detail || "Email o contraseña incorrectos");
  }
  if (!res.ok) throw new Error("Error de conexión");
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}
