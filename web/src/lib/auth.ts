const API_BASE = "";

export async function login(username: string, password: string): Promise<{ ok: boolean; username: string }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
    credentials: "include",
  });
  if (res.status === 401) {
    const err = await res.json();
    throw new Error(err.detail || "Usuario o contraseña incorrectos");
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
