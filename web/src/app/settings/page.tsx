"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchUsers, apiCreateUser, deleteUser, fetchCatalog, updateCatalog, type UserInfo } from "@/lib/api";
import { useToast } from "@/lib/toast-context";
import clsx from "clsx";

type Section = "usuarios" | "arquitectas" | "iva" | "descuentos" | "merma" | "placas" | "edificios" | "plazos" | "medidas" | "colocacion" | "empresa" | "condiciones";

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
