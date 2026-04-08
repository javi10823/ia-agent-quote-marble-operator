"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchUsers, apiCreateUser, deleteUser, fetchCatalog, updateCatalog, fetchUsageDashboard, fetchUsageDaily, updateUsageBudget, type UserInfo } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import clsx from "clsx";

type Section = "usuarios" | "arquitectas" | "iva" | "descuentos" | "merma" | "placas" | "edificios" | "plazos" | "medidas" | "colocacion" | "empresa" | "condiciones" | "motor_ia" | "api_usage";

const SECTIONS: { key: Section; label: string; icon: string }[] = [
  { key: "usuarios", label: "Usuarios", icon: "👤" },
  { key: "arquitectas", label: "Arquitectas", icon: "🏢" },
  { key: "iva", label: "IVA", icon: "💰" },
  { key: "descuentos", label: "Descuentos", icon: "🏷️" },
  { key: "merma", label: "Merma", icon: "📐" },
  { key: "placas", label: "Placas y Stock", icon: "🪨" },
  { key: "edificios", label: "Edificios", icon: "🏗️" },
  { key: "plazos", label: "Plazos", icon: "📅" },
  { key: "medidas", label: "Medidas", icon: "📏" },
  { key: "colocacion", label: "Colocación", icon: "🔧" },
  { key: "empresa", label: "Empresa", icon: "🏠" },
  { key: "condiciones", label: "Condiciones", icon: "📜" },
  { key: "motor_ia", label: "Motor IA", icon: "🤖" },
  { key: "api_usage", label: "Uso de API", icon: "📊" },
];

export default function SettingsPage() {
  const router = useRouter();
  const toast = useToast();
  const [section, setSection] = useState<Section>("usuarios");

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-4 md:px-7 pt-4 md:pt-5 pb-3 md:pb-[18px] border-b border-b1 shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/")} className="w-[30px] h-[30px] rounded-md border border-b1 bg-transparent text-t2 cursor-pointer flex items-center justify-center hover:border-b2 hover:text-t1 transition">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <div>
            <div className="text-lg font-medium -tracking-[0.03em]">Configuración</div>
            <div className="text-[11px] text-t3 mt-0.5">Parámetros del sistema y datos operativos</div>
          </div>
        </div>
      </div>

      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Nav */}
        <div className="md:w-[180px] shrink-0 bg-s1 border-b md:border-b-0 md:border-r border-b1 px-2 py-2 md:py-3 overflow-x-auto md:overflow-x-hidden overflow-y-hidden md:overflow-y-auto flex md:flex-col gap-0.5">
          {SECTIONS.map(s => (
            <button
              key={s.key}
              onClick={() => setSection(s.key)}
              className={clsx(
                "flex items-center gap-2 px-2.5 py-2 rounded-md text-xs cursor-pointer border-none whitespace-nowrap md:whitespace-normal md:w-full text-left font-sans transition-all",
                section === s.key ? "text-acc bg-acc-bg" : "text-t2 bg-transparent hover:bg-white/[0.04]",
              )}
            >
              <span className="w-5 text-center text-sm">{s.icon}</span> {s.label}
            </button>
          ))}
        </div>

        {/* Panel */}
        <div className="flex-1 overflow-y-auto px-4 md:px-7 py-4 md:py-6">
          {section === "usuarios" && <UsersSection toast={toast} />}
          {section === "arquitectas" && <ArchitectsSection toast={toast} />}
          {section === "iva" && <IvaSection toast={toast} />}
          {section === "descuentos" && <DiscountsSection toast={toast} />}
          {section === "merma" && <MermaSection toast={toast} />}
          {section === "placas" && <PlacasStockSection toast={toast} />}
          {section === "edificios" && <BuildingSection toast={toast} />}
          {section === "plazos" && <DeliverySection toast={toast} />}
          {section === "medidas" && <MeasurementsSection toast={toast} />}
          {section === "colocacion" && <ColocacionSection toast={toast} />}
          {section === "empresa" && <CompanySection toast={toast} />}
          {section === "condiciones" && <ConditionsSection toast={toast} />}
          {section === "motor_ia" && <MotorIASection toast={toast} />}
          {section === "api_usage" && <ApiUsageSection toast={toast} />}
        </div>
      </div>
    </div>
  );
}

// ── USUARIOS ────────────────────────────────────────────────────────────────

function UsersSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => { fetchUsers().then(setUsers).catch(() => toast("Error al cargar usuarios")); }, [toast]);

  async function handleCreate() {
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    try {
      await apiCreateUser(username.trim(), password);
      toast("Usuario creado", "success");
      setUsername(""); setPassword("");
      setUsers(await fetchUsers());
    } catch (err: any) { toast(err.message); }
    finally { setLoading(false); }
  }

  async function handleDelete(id: string, name: string) {
    if (!window.confirm(`¿Eliminar usuario "${name}"?`)) return;
    try {
      await deleteUser(id);
      toast("Usuario eliminado", "success");
      setUsers(await fetchUsers());
    } catch (err: any) { toast(err.message); }
  }

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Usuarios del sistema</div>
      <div className="text-xs text-t3 mb-5">Operadores con acceso al panel de presupuestos.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <table className="w-full border-collapse">
          <thead><tr>
            <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Usuario</th>
            <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Creado</th>
            <th className="px-3 py-2 border-b border-b1 w-20"></th>
          </tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className="hover:bg-white/[0.02]">
                <td className="px-3 py-2.5 text-[13px] font-medium text-t1">{u.username}</td>
                <td className="px-3 py-2.5 text-xs text-t3">{u.created_at ? new Date(u.created_at).toLocaleDateString("es-AR") : "—"}</td>
                <td className="px-3 py-2.5 text-right">
                  <button onClick={() => handleDelete(u.id, u.username)} className="px-2.5 py-1 rounded-md text-[11px] font-medium border border-err/30 bg-transparent text-err cursor-pointer hover:bg-err/[0.08] transition">Eliminar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px]">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Agregar usuario</div>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">Usuario</label>
            <input value={username} onChange={e => setUsername(e.target.value)} placeholder="nombre de usuario" className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4" />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">Contraseña</label>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="min. 6 caracteres" className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4" />
          </div>
        </div>
        <button onClick={handleCreate} disabled={loading} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
          {loading ? "Creando..." : "Crear usuario"}
        </button>
      </div>
    </>
  );
}

// ── ARQUITECTAS ─────────────────────────────────────────────────────────────

function ArchitectsSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const [architects, setArchitects] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [firm, setFirm] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => { fetchCatalog("architects").then(setArchitects).catch(() => toast("Error al cargar arquitectas")); }, [toast]);

  async function handleAdd() {
    if (!name.trim()) return;
    const updated = [...architects, { name: name.trim().toUpperCase(), firm: firm.trim() || null, discount: true, discount_percentage: null, notes: notes.trim() || null }];
    try {
      await updateCatalog("architects", updated);
      setArchitects(updated);
      setName(""); setFirm(""); setNotes("");
      toast("Arquitecta agregada", "success");
    } catch (err: any) { toast(err.message); }
  }

  async function handleRemove(idx: number) {
    const a = architects[idx];
    if (!window.confirm(`¿Quitar a "${a.name}"?`)) return;
    const updated = architects.filter((_, i) => i !== idx);
    try {
      await updateCatalog("architects", updated);
      setArchitects(updated);
      toast("Arquitecta eliminada", "success");
    } catch (err: any) { toast(err.message); }
  }

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Arquitectas con descuento</div>
      <div className="text-xs text-t3 mb-5">Clientes registrados como arquitectos. El descuento se aplica automáticamente al detectar el nombre.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <table className="w-full border-collapse">
          <thead><tr>
            <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Nombre</th>
            <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Estudio</th>
            <th className="text-left px-3 py-2 text-[10px] font-semibold text-t3 uppercase tracking-wide border-b border-b1">Notas</th>
            <th className="px-3 py-2 border-b border-b1 w-16"></th>
          </tr></thead>
          <tbody>
            {architects.map((a: any, i: number) => (
              <tr key={i} className="hover:bg-white/[0.02]">
                <td className="px-3 py-2.5 text-[13px] font-medium text-t1">{a.name}</td>
                <td className="px-3 py-2.5 text-xs text-t3">{a.firm || "—"}</td>
                <td className="px-3 py-2.5 text-xs text-t3">{a.notes || "—"}</td>
                <td className="px-3 py-2.5 text-right">
                  <button onClick={() => handleRemove(i)} className="px-2.5 py-1 rounded-md text-[11px] font-medium border border-err/30 bg-transparent text-err cursor-pointer hover:bg-err/[0.08] transition">Quitar</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px]">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Agregar arquitecta</div>
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">Nombre</label>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="ARQ. NOMBRE" className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4" />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">Estudio (opc)</label>
            <input value={firm} onChange={e => setFirm(e.target.value)} placeholder="Nombre del estudio" className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4" />
          </div>
          <div>
            <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">Notas (opc)</label>
            <input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Referencia interna" className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4" />
          </div>
        </div>
        <button onClick={handleAdd} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition">Agregar</button>
      </div>
    </>
  );
}

// ── CONFIG SECTION (shared pattern for descuentos/plazos/empresa/condiciones) ──

function useConfigSection(sectionKey: string, toast: (m: string, v?: "error" | "success" | "warning") => void) {
  const [config, setConfig] = useState<any>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchCatalog("config").then(setConfig).catch(() => toast("Error al cargar config"));
  }, [toast]);

  async function save(updated: any) {
    setSaving(true);
    try {
      await updateCatalog("config", updated);
      setConfig(updated);
      toast("Guardado", "success");
    } catch (err: any) { toast(err.message); }
    finally { setSaving(false); }
  }

  return { config, setConfig, saving, save };
}

// ── DESCUENTOS ──────────────────────────────────────────────────────────────

function DiscountsSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("discount", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const d = config.discount || {};
  const upd = (key: string, val: number) => setConfig({ ...config, discount: { ...config.discount, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Parámetros de descuento</div>
      <div className="text-xs text-t3 mb-5">Porcentajes y umbrales que Valentina usa al calcular descuentos automáticos.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Descuento arquitecta</div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="% Material importado (USD)" type="number" value={d.imported_percentage} onChange={v => upd("imported_percentage", +v)} />
          <Field label="% Material nacional (ARS)" type="number" value={d.national_percentage} onChange={v => upd("national_percentage", +v)} />
          <Field label="Umbral mínimo m²" type="number" value={d.min_m2_threshold} onChange={v => upd("min_m2_threshold", +v)} />
        </div>
      </div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Descuento edificio</div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="% Descuento edificio" type="number" value={d.building_percentage} onChange={v => upd("building_percentage", +v)} />
          <Field label="Umbral mínimo m²" type="number" value={d.building_min_m2_threshold} onChange={v => upd("building_min_m2_threshold", +v)} />
        </div>
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── PLAZOS ──────────────────────────────────────────────────────────────────

function DeliverySection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("delivery_days", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const dd = config.delivery_days || {};
  const upd = (key: string, val: any) => setConfig({ ...config, delivery_days: { ...config.delivery_days, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Plazo de entrega</div>
      <div className="text-xs text-t3 mb-5">Días y texto que aparecen como default en los presupuestos.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Días default" type="number" value={dd.default} onChange={v => upd("default", +v)} />
          <Field label="Texto para presupuesto" value={dd.display} onChange={v => upd("display", v)} />
        </div>
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── EMPRESA ─────────────────────────────────────────────────────────────────

function CompanySection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("company", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const c = config.company || {};
  const upd = (key: string, val: string) => setConfig({ ...config, company: { ...config.company, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Datos de la empresa</div>
      <div className="text-xs text-t3 mb-5">Información que aparece en el encabezado de cada PDF generado.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="grid grid-cols-2 gap-3 mb-3">
          <Field label="Nombre" value={c.name} onChange={v => upd("name", v)} />
          <Field label="Subtítulo" value={c.subtitle} onChange={v => upd("subtitle", v)} />
        </div>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <Field label="Dirección" value={c.address} onChange={v => upd("address", v)} />
          <Field label="Teléfono" value={c.phone} onChange={v => upd("phone", v)} />
        </div>
        <Field label="Email" value={c.email} onChange={v => upd("email", v)} />
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── CONDICIONES ─────────────────────────────────────────────────────────────

function ConditionsSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("conditions", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const cond = config.conditions || {};
  const upd = (key: string, val: string) => setConfig({ ...config, conditions: { ...config.conditions, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Condiciones del presupuesto</div>
      <div className="text-xs text-t3 mb-5">Texto legal y formas de pago que aparecen en el pie de cada PDF.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Condiciones generales</div>
        <textarea
          value={cond.general || ""}
          onChange={e => upd("general", e.target.value)}
          rows={6}
          className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t2 text-xs font-sans outline-none focus:border-acc resize-y min-h-[80px] leading-[1.6]"
        />
      </div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Formas de pago</div>
        <textarea
          value={cond.payment || ""}
          onChange={e => upd("payment", e.target.value)}
          rows={4}
          className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t2 text-xs font-sans outline-none focus:border-acc resize-y min-h-[80px] leading-[1.6]"
        />
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── MEDIDAS (defaults) ─────────────────────────────────────────────────────

function MeasurementsSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("measurements", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const m = config.measurements || {};
  const upd = (key: string, val: number) => setConfig({ ...config, measurements: { ...config.measurements, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Medidas por defecto</div>
      <div className="text-xs text-t3 mb-5">Valores que Valentina usa cuando el operador no especifica una medida.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="grid grid-cols-3 gap-3">
          <Field label="Profundidad mesada (m)" type="number" value={m.default_depth} onChange={v => upd("default_depth", +v)} />
          <Field label="Alto zócalo (m)" type="number" value={m.default_zocalo_height} onChange={v => upd("default_zocalo_height", +v)} />
          <Field label="Umbral zócalo alto (m)" type="number" value={m.tall_zocalo_threshold} onChange={v => upd("tall_zocalo_threshold", +v)} />
        </div>
        <div className="text-[11px] text-t4 mt-2">Umbral zócalo alto: si el alto supera este valor, se agrega 1 toma de corriente automáticamente.</div>
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── COLOCACIÓN ─────────────────────────────────────────────────────────────

function ColocacionSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("colocacion", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const c = config.colocacion || {};
  const upd = (key: string, val: number) => setConfig({ ...config, colocacion: { ...config.colocacion, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Colocación</div>
      <div className="text-xs text-t3 mb-5">Parámetros de cálculo de mano de obra por colocación.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <Field label="Cantidad mínima m²" type="number" value={c.min_quantity} onChange={v => upd("min_quantity", +v)} />
        <div className="text-[11px] text-t4 mt-2">Si el total de m² es menor a este valor, se cobra este mínimo.</div>
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── IVA ────────────────────────────────────────────────────────────────────

function IvaSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("iva", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const iva = config.iva || {};
  const upd = (key: string, val: number) => setConfig({ ...config, iva: { ...config.iva, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">IVA</div>
      <div className="text-xs text-t3 mb-5">Alícuota de IVA aplicada a todos los precios de catálogo.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Multiplicador (ej: 1.21)" type="number" value={iva.multiplier} onChange={v => upd("multiplier", +v)} />
          <Field label="Porcentaje (%)" type="number" value={iva.percentage} onChange={v => upd("percentage", +v)} />
        </div>
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── MERMA ──────────────────────────────────────────────────────────────────

function MermaSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("merma", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const m = config.merma || {};
  const upd = (key: string, val: number) => setConfig({ ...config, merma: { ...config.merma, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Merma</div>
      <div className="text-xs text-t3 mb-5">Umbral de desperdicio para materiales sintéticos. Solo aplica a Silestone, Dekton, Neolith, Puraprima, Purastone, Laminatto.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <Field label="Umbral pieza chica (m²)" type="number" value={m.small_piece_threshold_m2} onChange={v => upd("small_piece_threshold_m2", +v)} />
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── PLACAS Y STOCK ─────────────────────────────────────────────────────────

function PlacasStockSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("plate_sizes", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const ps = config.plate_sizes || {};
  const stock = config.stock || {};
  const updPlate = (size: string, key: string, val: number) => setConfig({
    ...config,
    plate_sizes: { ...config.plate_sizes, [size]: { ...config.plate_sizes[size], [key]: val } },
  });
  const updStock = (key: string, val: boolean) => setConfig({ ...config, stock: { ...config.stock, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Tamaños de placa</div>
      <div className="text-xs text-t3 mb-5">Dimensiones de las placas estándar y especial para cálculo de merma.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Placa estándar</div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Largo (m)" type="number" value={ps.estandar?.largo} onChange={v => updPlate("estandar", "largo", +v)} />
          <Field label="Ancho (m)" type="number" value={ps.estandar?.ancho} onChange={v => updPlate("estandar", "ancho", +v)} />
          <Field label="m² total" type="number" value={ps.estandar?.m2} onChange={v => updPlate("estandar", "m2", +v)} />
        </div>
      </div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Placa especial</div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Largo (m)" type="number" value={ps.especial?.largo} onChange={v => updPlate("especial", "largo", +v)} />
          <Field label="Ancho (m)" type="number" value={ps.especial?.ancho} onChange={v => updPlate("especial", "ancho", +v)} />
          <Field label="m² total" type="number" value={ps.especial?.m2} onChange={v => updPlate("especial", "m2", +v)} />
        </div>
      </div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="text-[13px] font-semibold text-t1 mb-3 pb-2 border-b border-b1">Stock default</div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={stock.default ?? false}
              onChange={e => updStock("default", e.target.checked)}
              className="w-4 h-4 accent-acc"
            />
            <span className="text-[13px] text-t2">Material en stock por defecto (si está en stock, NO aplica merma)</span>
          </label>
        </div>
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── EDIFICIOS ──────────────────────────────────────────────────────────────

function BuildingSection({ toast }: { toast: (m: string, v?: "error" | "success" | "warning") => void }) {
  const { config, setConfig, saving, save } = useConfigSection("building", toast);
  if (!config) return <div className="text-t3 text-[13px]">Cargando...</div>;

  const b = config.building || {};
  const upd = (key: string, val: any) => setConfig({ ...config, building: { ...config.building, [key]: val } });

  return (
    <>
      <div className="text-[15px] font-semibold text-t1 mb-1">Reglas para edificios</div>
      <div className="text-xs text-t3 mb-5">Parámetros especiales cuando el trabajo es en un edificio/obra.</div>

      <div className="bg-s1 border border-b1 rounded-[10px] p-[18px] mb-4">
        <div className="grid grid-cols-2 gap-3 mb-3">
          <Field label="% Descuento edificio" type="number" value={b.discount_percentage} onChange={v => upd("discount_percentage", +v)} />
          <Field label="Mínimo m² para descuento" type="number" value={b.discount_min_m2} onChange={v => upd("discount_min_m2", +v)} />
        </div>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <Field label="Mesadas por viaje (flete)" type="number" value={b.flete_mesadas_per_trip} onChange={v => upd("flete_mesadas_per_trip", +v)} />
          <div className="mb-1 flex items-end">
            <label className="flex items-center gap-2 cursor-pointer pb-2">
              <input
                type="checkbox"
                checked={b.colocacion ?? false}
                onChange={e => upd("colocacion", e.target.checked)}
                className="w-4 h-4 accent-acc"
              />
              <span className="text-[13px] text-t2">Con colocación</span>
            </label>
          </div>
        </div>
      </div>

      <button onClick={() => save(config)} disabled={saving} className="px-3.5 py-[7px] rounded-md text-xs font-medium bg-acc text-white border-none cursor-pointer hover:bg-[#3d7be6] transition disabled:opacity-50">
        {saving ? "Guardando..." : "Guardar cambios"}
      </button>
    </>
  );
}

// ── SHARED FIELD COMPONENT ──────────────────────────────────────────────────

function Field({ label, value, onChange, type = "text" }: { label: string; value: any; onChange: (v: string) => void; type?: string }) {
  return (
    <div className="mb-1">
      <label className="block text-[11px] font-medium text-t3 uppercase tracking-wide mb-1">{label}</label>
      <input
        type={type}
        value={value ?? ""}
        onChange={e => onChange(e.target.value)}
        className="w-full px-3 py-2 bg-s3 border border-b1 rounded-lg text-t1 text-[13px] font-sans outline-none focus:border-acc placeholder:text-t4"
      />
    </div>
  );
}


// ── Motor IA Section ─────────────────────────────────────────────────────────

function MotorIASection({ toast }: { toast: (msg: string) => void }) {
  const [config, setConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchCatalog("config").then(data => {
      const cfg = Array.isArray(data) ? data[0] || {} : data;
      setConfig(cfg);
    }).catch(() => toast("Error cargando config")).finally(() => setLoading(false));
  }, []);

  const aiEngine = config.ai_engine || { use_opus_for_plans: true, rotate_plan_images: true, max_examples: 1 };

  const updateToggle = async (key: string, value: boolean | number) => {
    const updated = { ...config, ai_engine: { ...aiEngine, [key]: value } };
    setConfig(updated);
    setSaving(true);
    try {
      await updateCatalog("config", updated);
      toast("Configuración guardada");
    } catch { toast("Error al guardar"); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="text-t3 text-[13px]">Cargando...</div>;

  return (
    <div>
      <h2 className="text-[15px] font-medium text-t1 mb-1">Motor IA</h2>
      <p className="text-[12px] text-t3 mb-5">Configuración del motor de inteligencia artificial. Afecta costo y precisión.</p>

      <div className="flex flex-col gap-4">
        <Toggle
          label="Usar Opus para planos"
          description="Usa Claude Opus 4.6 (más preciso, 3x más caro) para leer planos. Si está desactivado, usa Sonnet."
          checked={aiEngine.use_opus_for_plans ?? true}
          onChange={v => updateToggle("use_opus_for_plans", v)}
        />
        <Toggle
          label="Rotar imágenes de planos"
          description="Envía una versión rotada 90° de cada plano para leer texto en los márgenes. Duplica tokens de imagen."
          checked={aiEngine.rotate_plan_images ?? true}
          onChange={v => updateToggle("rotate_plan_images", v)}
        />
        <div className="bg-s2 border border-b1 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[13px] font-medium text-t1">Ejemplos por request</div>
              <div className="text-[11px] text-t3 mt-0.5">Cantidad de ejemplos de presupuestos incluidos en cada mensaje. Más = más preciso pero más caro.</div>
            </div>
            <select
              value={aiEngine.max_examples ?? 1}
              onChange={e => updateToggle("max_examples", parseInt(e.target.value))}
              className="bg-s3 border border-b1 rounded-md text-t1 text-[13px] px-2 py-1 outline-none"
            >
              <option value={0}>0 (sin ejemplos)</option>
              <option value={1}>1 (recomendado)</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
          </div>
        </div>
      </div>

      {saving && <div className="text-[11px] text-acc mt-3">Guardando...</div>}
    </div>
  );
}

// ── API Usage Section ────────────────────────────────────────────────────────

function ApiUsageSection({ toast }: { toast: (msg: string) => void }) {
  const [dashboard, setDashboard] = useState<any>(null);
  const [daily, setDaily] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editLimit, setEditLimit] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([fetchUsageDashboard(), fetchUsageDaily()])
      .then(([d, dd]) => { setDashboard(d); setDaily(dd); setEditLimit(String(d.limit_usd)); })
      .catch(() => toast("Error cargando datos de uso"))
      .finally(() => setLoading(false));
  }, []);

  const saveLimit = async () => {
    setSaving(true);
    try {
      await updateUsageBudget({ monthly_budget_usd: parseFloat(editLimit) });
      const d = await fetchUsageDashboard();
      setDashboard(d);
      toast("Límite actualizado");
    } catch { toast("Error"); }
    finally { setSaving(false); }
  };

  const toggleHardLimit = async (v: boolean) => {
    await updateUsageBudget({ enable_hard_limit: v });
    const d = await fetchUsageDashboard();
    setDashboard(d);
  };

  if (loading) return <div className="text-t3 text-[13px]">Cargando...</div>;
  if (!dashboard) return <div className="text-t3 text-[13px]">Sin datos</div>;

  const { spent_usd, limit_usd, pct_used, daily_avg, daily_budget, projected, days_passed, days_left, requests, alert } = dashboard;
  const barColor = alert === "blocked" ? "bg-red" : alert === "red" ? "bg-red" : alert === "yellow" ? "bg-amb" : "bg-grn";
  const alertMsg = alert === "blocked" ? "BLOQUEADO — Límite mensual alcanzado"
    : alert === "red" ? `A este ritmo ($${daily_avg.toFixed(2)}/día) se proyectan $${projected.toFixed(2)} — EXCEDE el límite`
    : alert === "yellow" ? "Cerca del límite (>80%)"
    : "Consumo normal";

  return (
    <div>
      <h2 className="text-[15px] font-medium text-t1 mb-1">Uso de API</h2>
      <p className="text-[12px] text-t3 mb-5">Consumo de la API de Anthropic (Claude) este mes.</p>

      {/* Main card */}
      <div className={clsx("bg-s2 border rounded-xl p-5 mb-4", alert === "red" || alert === "blocked" ? "border-red/40" : alert === "yellow" ? "border-amb/40" : "border-b1")}>
        <div className="flex items-end justify-between mb-3">
          <div>
            <div className="text-[28px] font-bold text-t1 font-mono">${spent_usd.toFixed(2)}</div>
            <div className="text-[12px] text-t3">de ${limit_usd.toFixed(2)} este mes</div>
          </div>
          <div className="text-right">
            <div className="text-[13px] text-t2">{requests} requests</div>
            <div className="text-[11px] text-t3">{days_passed} días, {days_left} restantes</div>
          </div>
        </div>
        {/* Progress bar */}
        <div className="w-full h-2 bg-white/[0.06] rounded-full overflow-hidden mb-3">
          <div className={clsx("h-full rounded-full transition-all", barColor)} style={{ width: `${Math.min(pct_used, 100)}%` }} />
        </div>
        {/* Alert */}
        <div className={clsx("text-[12px] font-medium px-3 py-2 rounded-lg", alert === "red" || alert === "blocked" ? "bg-red/10 text-red" : alert === "yellow" ? "bg-amb/10 text-amb" : "bg-grn/10 text-grn")}>
          {alertMsg}
        </div>
        {/* Stats row */}
        <div className="flex gap-4 mt-4 text-[11px] text-t3">
          <div>Promedio: <span className="text-t1 font-mono">${daily_avg.toFixed(2)}/día</span></div>
          <div>Presupuesto: <span className="text-t1 font-mono">${daily_budget.toFixed(2)}/día</span></div>
          <div>Proyección: <span className={clsx("font-mono", projected > limit_usd ? "text-red" : "text-t1")}>${projected.toFixed(2)}</span></div>
        </div>
      </div>

      {/* Budget config */}
      <div className="bg-s2 border border-b1 rounded-xl p-4 mb-4">
        <div className="text-[13px] font-medium text-t1 mb-3">Configuración</div>
        <div className="flex items-center gap-3 mb-3">
          <span className="text-[12px] text-t3 shrink-0">Límite mensual:</span>
          <input value={editLimit} onChange={e => setEditLimit(e.target.value)} type="number" step="5" min="0"
            className="w-24 px-2 py-1 bg-s3 border border-b1 rounded-md text-t1 text-[13px] outline-none" />
          <span className="text-[12px] text-t3">USD</span>
          <button onClick={saveLimit} disabled={saving}
            className="px-3 py-1 bg-acc border-none rounded-md text-white text-[11px] font-medium cursor-pointer">
            {saving ? "..." : "Guardar"}
          </button>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[12px] text-t2">Bloqueo automático</div>
            <div className="text-[10px] text-t3">Bloquea requests cuando se excede el límite</div>
          </div>
          <button onClick={() => toggleHardLimit(!dashboard.enable_hard_limit)}
            className={clsx("w-10 h-[22px] rounded-full border-none cursor-pointer transition-colors shrink-0 relative", dashboard.enable_hard_limit ? "bg-acc" : "bg-white/[0.12]")}>
            <div className={clsx("w-[18px] h-[18px] rounded-full bg-white absolute top-[2px] transition-[left]", dashboard.enable_hard_limit ? "left-[20px]" : "left-[2px]")} />
          </button>
        </div>
      </div>

      {/* Daily breakdown */}
      <div className="bg-s2 border border-b1 rounded-xl p-4">
        <div className="text-[13px] font-medium text-t1 mb-3">Consumo diario (últimos 30 días)</div>
        {daily.length === 0 ? (
          <div className="text-[12px] text-t3">Sin datos aún</div>
        ) : (
          <div className="max-h-[300px] overflow-y-auto">
            <table className="w-full text-[12px]">
              <thead><tr className="text-t3 text-left">
                <th className="pb-2 font-medium">Fecha</th>
                <th className="pb-2 font-medium text-right">Costo</th>
                <th className="pb-2 font-medium text-right">Requests</th>
                <th className="pb-2 font-medium text-right">Tokens</th>
              </tr></thead>
              <tbody>{daily.map((d: any) => (
                <tr key={d.date} className="border-t border-white/[0.04]">
                  <td className="py-1.5 text-t2">{d.date}</td>
                  <td className={clsx("py-1.5 text-right font-mono", d.cost_usd > daily_budget ? "text-red" : "text-t1")}>${d.cost_usd.toFixed(3)}</td>
                  <td className="py-1.5 text-right text-t3">{d.requests}</td>
                  <td className="py-1.5 text-right text-t3">{((d.input_tokens + d.output_tokens) / 1000).toFixed(0)}K</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}


function Toggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="bg-s2 border border-b1 rounded-lg p-4 flex items-center justify-between gap-4">
      <div>
        <div className="text-[13px] font-medium text-t1">{label}</div>
        <div className="text-[11px] text-t3 mt-0.5">{description}</div>
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={clsx(
          "w-10 h-[22px] rounded-full border-none cursor-pointer transition-colors shrink-0 relative",
          checked ? "bg-acc" : "bg-white/[0.12]"
        )}
      >
        <div className={clsx(
          "w-[18px] h-[18px] rounded-full bg-white absolute top-[2px] transition-[left]",
          checked ? "left-[20px]" : "left-[2px]"
        )} />
      </button>
    </div>
  );
}
