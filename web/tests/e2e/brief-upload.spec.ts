/**
 * E2E del paso 1 — brief upload.
 *
 * Cubre los 3 estados visuales (mockups 00 A/B/C), validaciones,
 * cancel y success path.
 *
 * El "backend" es el mock client en lib/v2/api.ts con latencia
 * 2-5s + AbortController. NO toca backend real.
 */
import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const FIXTURE_PDF = path.join(__dirname, "..", "fixtures", "sample.pdf");

async function uploadPdf(page: Page, file: string = FIXTURE_PDF) {
  await page.locator('[data-testid="brief-dropzone-input"]').setInputFiles(file);
}

test("estado A — dropzone vacío al cargar /quotes/new", async ({ page }) => {
  await page.goto("/quotes/new");
  await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).not.toBeVisible();
  await expect(page.locator('[data-testid="brief-status-bar"]')).not.toBeVisible();
  await expect(page.locator(".brief-hero h2")).toContainText("Subí lo que tengas");
});

test("estado A → B — al subir un PDF aparece el form con el filename", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-name"]')).toHaveText("sample.pdf");
  await expect(page.locator(".brief-hero h2")).toContainText("Tengo todo lo que necesito");
  await expect(page.locator('[data-testid="brief-submit"]')).toBeEnabled();
});

test("validación — PDF tipo inválido (txt) rechazado en estado A", async ({ page }) => {
  await page.goto("/quotes/new");
  await page.locator('[data-testid="brief-dropzone-input"]').setInputFiles({
    name: "wrong.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("no soy un PDF"),
  });
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toContainText("PDF");
  // Sigue en estado A (no avanzó)
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).not.toBeVisible();
});

test("validación — PDF > 10MB rechazado en estado A", async ({ page }) => {
  // Sprint 4 paso-1-chips-brief-libre: límite ajustado a 10MB LITERAL del
  // mockup oficial (dz-sub "PDF · máx. 10 MB · ..."). Antes 20MB.
  await page.goto("/quotes/new");
  const big = Buffer.alloc(11 * 1024 * 1024, 0);
  await page.locator('[data-testid="brief-dropzone-input"]').setInputFiles({
    name: "huge.pdf",
    mimeType: "application/pdf",
    buffer: big,
  });
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-dropzone-error"]')).toContainText("10");
});

test("validación — foto tipo inválido rechazada", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="photo-input"]').setInputFiles({
    name: "wrong.gif",
    mimeType: "image/gif",
    buffer: Buffer.from("fake"),
  });
  await expect(page.locator('[data-testid="brief-helper"]')).toContainText(/JPG|PNG/);
});

test("estado B → C — click Procesar muestra skeleton + status-bar", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-submit"]').click();
  await expect(page.locator('[data-testid="brief-status-bar"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-processing"]')).toBeVisible();
  await expect(page.locator(".skel").first()).toBeVisible();
});

test("cancel — estado C → vuelve a B con planFile preservado", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-submit"]').click();
  await expect(page.locator('[data-testid="brief-status-bar"]')).toBeVisible();
  await page.locator('[data-testid="brief-cancel"]').click();
  // Vuelve a estado B con el form intacto
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-name"]')).toHaveText("sample.pdf");
  await expect(page.locator('[data-testid="brief-status-bar"]')).not.toBeVisible();
});

test("success path — completar el flujo navega a /quotes/PRES-2026-018/contexto", async ({
  page,
}) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-text"]').fill("Cocina U + isla, 3,20m");
  await page.locator('[data-testid="brief-submit"]').click();
  // Mock simula latencia 2-5s — esperar redirect (timeout 10s safety)
  await page.waitForURL("**/quotes/PRES-2026-018/contexto", { timeout: 10000 });
  // Confirmar que el chrome del [id] layout está activo
  await expect(page.locator(".stepper")).toHaveAttribute("data-current-step", "contexto");
});

test("CTA en /v2 navega a /quotes/new", async ({ page }) => {
  await page.goto("/");
  await page.locator('[data-testid="cta-new-quote"]').click();
  await page.waitForURL("**/quotes/new");
  await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
});

/* ─── Sprint 4 paso-1-chips-brief-libre · LITERAL mockup A/B/C ─────── */

test("Estado A · 3 brief-chips Cliente/Ambiente/Plazo opcionales renderean", async ({ page }) => {
  await page.goto("/quotes/new");
  await expect(page.locator('[data-testid="brief-chip-cliente"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-chip-ambiente"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-chip-plazo"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-chip-cliente-input"]')).toHaveAttribute(
    "placeholder",
    "opcional · ej. Cueto-Heredia",
  );
  await expect(page.locator('[data-testid="brief-chip-ambiente-input"]')).toHaveAttribute(
    "placeholder",
    "opcional · ej. cocina",
  );
  await expect(page.locator('[data-testid="brief-chip-plazo-input"]')).toHaveAttribute(
    "placeholder",
    "opcional · ej. 3 semanas",
  );
});

test("Estado A · brief-textarea-wrap con placeholder LITERAL del mockup", async ({ page }) => {
  await page.goto("/quotes/new");
  await expect(page.locator('[data-testid="brief-text"]')).toHaveAttribute(
    "placeholder",
    /Pegá acá el WhatsApp del cliente/,
  );
});

test("Estado A · CTA disabled cuando todo vacío + helper LITERAL", async ({ page }) => {
  await page.goto("/quotes/new");
  await expect(page.locator('[data-testid="brief-submit"]')).toBeDisabled();
  await expect(page.locator('[data-testid="brief-helper"]')).toContainText(/Necesito al menos el/);
});

test("Estado A · llenar 3 chips sin PDF habilita CTA (cliente+ambiente)", async ({ page }) => {
  await page.goto("/quotes/new");
  await page.locator('[data-testid="brief-chip-cliente-input"]').fill("Cueto-Heredia");
  await page.locator('[data-testid="brief-chip-ambiente-input"]').fill("cocina");
  await expect(page.locator('[data-testid="brief-submit"]')).toBeEnabled();
});

test("Estado A · solo chip cliente (sin ambiente) NO habilita CTA", async ({ page }) => {
  await page.goto("/quotes/new");
  await page.locator('[data-testid="brief-chip-cliente-input"]').fill("X");
  await expect(page.locator('[data-testid="brief-submit"]')).toBeDisabled();
});

test("Estado A · textarea ≥50 chars sin PDF habilita CTA + helper cambia", async ({ page }) => {
  await page.goto("/quotes/new");
  await page
    .locator('[data-testid="brief-text"]')
    .fill("Cocina U en Belgrano, Silestone Blanco Norte, 3.20m mesada bacha empotrada");
  await expect(page.locator('[data-testid="brief-submit"]')).toBeEnabled();
  await expect(page.locator('[data-testid="brief-helper"]')).toContainText(
    /Sin plano voy a intentar igual/,
  );
});

test("Estado A · textarea <50 chars sin PDF mantiene CTA disabled", async ({ page }) => {
  await page.goto("/quotes/new");
  await page.locator('[data-testid="brief-text"]').fill("hola");
  await expect(page.locator('[data-testid="brief-submit"]')).toBeDisabled();
});

test("Estado B · subir PDF muestra dropzone.loaded + botones Reemplazar/Quitar", async ({
  page,
}) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-replace"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-replace"]')).toContainText("Reemplazar");
  await expect(page.locator('[data-testid="brief-plan-reset"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-plan-reset"]')).toContainText("✕ Quitar");
});

test("Estado B · click Quitar pide confirm() destructivo y vuelve a A", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  page.on("dialog", (d) => d.accept());
  await page.locator('[data-testid="brief-plan-reset"]').click();
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).not.toBeVisible();
  await expect(page.locator('[data-testid="brief-dropzone"]')).toBeVisible();
});

test("Estado B · label del textarea cambia a 'WhatsApp del estudio (hh:mm)'", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await expect(page.locator(".brief-textarea-wrap .lbl").first()).toContainText(
    /WhatsApp del estudio \(\d{2}:\d{2}\)/,
  );
});

test("Estado B · botón ghost 'Cargar a mano →' visible + dispara submitManual", async ({
  page,
}) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await expect(page.locator('[data-testid="brief-submit-manual"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-submit-manual"]')).toContainText("Cargar a mano");
  await page.locator('[data-testid="brief-submit-manual"]').click();
  // Mock crea draft + redirect a /contexto
  await page.waitForURL(/\/quotes\/.+\/contexto/, { timeout: 10_000 });
});

test("Estado A · link 'cargá a mano →' en lead dispara submitManual", async ({ page }) => {
  await page.goto("/quotes/new");
  await page.locator('[data-testid="brief-manual-hero-link"]').click();
  await page.waitForURL(/\/quotes\/.+\/contexto/, { timeout: 10_000 });
});

test("Estado A · link 'cargá a mano →' en helper dispara submitManual", async ({ page }) => {
  await page.goto("/quotes/new");
  await page.locator('[data-testid="brief-manual-helper-link"]').click();
  await page.waitForURL(/\/quotes\/.+\/contexto/, { timeout: 10_000 });
});

test("Estado C · timer dinámico en status-msg actualiza segundos", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-submit"]').click();
  const timer = page.locator('[data-testid="brief-status-timer"]');
  await expect(timer).toBeVisible();
  await expect(timer).toContainText(/\(\d+ s · esto suele tardar 12 s, dame uno más\)/);
});

test("Estado C · brief-status snapshot LITERAL del mockup visible", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-submit"]').click();
  await expect(page.locator('[data-testid="brief-status-snapshot"]')).toContainText(
    "3 datos del WhatsApp ya extraídos",
  );
  await expect(page.locator('[data-testid="brief-status-snapshot"]')).toContainText(
    "arquitecta encontrada",
  );
});

test("Estado C · ph-head incluye '· 3 hojas · página 1/3'", async ({ page }) => {
  await page.goto("/quotes/new");
  await uploadPdf(page);
  await page.locator('[data-testid="brief-submit"]').click();
  await expect(page.locator(".ph-head")).toContainText("· 3 hojas · página 1/3");
});

test("Persistencia A↔B · chips llenos en A se mantienen al subir PDF (estado B)", async ({
  page,
}) => {
  await page.goto("/quotes/new");
  await page.locator('[data-testid="brief-chip-cliente-input"]').fill("Cueto-Heredia");
  await page.locator('[data-testid="brief-chip-ambiente-input"]').fill("cocina");
  await page.locator('[data-testid="brief-text"]').fill("brief preservado");
  await uploadPdf(page);
  await expect(page.locator('[data-testid="brief-plan-loaded"]')).toBeVisible();
  await expect(page.locator('[data-testid="brief-chip-cliente-input"]')).toHaveValue(
    "Cueto-Heredia",
  );
  await expect(page.locator('[data-testid="brief-chip-ambiente-input"]')).toHaveValue("cocina");
  await expect(page.locator('[data-testid="brief-text"]')).toHaveValue("brief preservado");
});

test("Estado A · h2 LITERAL 'Subí lo que tengas y arranco' + lead con 'cargá a mano →'", async ({
  page,
}) => {
  await page.goto("/quotes/new");
  await expect(page.locator(".brief-hero h2")).toContainText("Subí lo que tengas y arranco");
  await expect(page.locator(".brief-hero .lead")).toContainText("cargá a mano");
});
