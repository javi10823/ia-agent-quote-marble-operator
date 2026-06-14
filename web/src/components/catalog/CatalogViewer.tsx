/**
 * CatalogViewer · sub-PR 22.2.b · viewer JSON read-only + backups + restore.
 *
 * GET /api/catalog/{name} → JSON crudo (read-only · sin editor manual).
 * GET /api/catalog/backups/{name} → últimas 20 versiones · cada una
 * restaurable (POST /backups/{id}/restore · el backend auto-backupea el
 * estado actual antes de restaurar · safety net).
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import { getCatalog, listBackups, restoreBackup } from "@/lib/api";
import type { CatalogBackup } from "@/lib/api/types";

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diffMs = Date.now() - t;
  const day = 86_400_000;
  if (diffMs < 0) return new Date(iso).toLocaleString();
  if (diffMs < day) return "hoy";
  const days = Math.floor(diffMs / day);
  if (days === 1) return "ayer";
  if (days < 30) return `hace ${days} días`;
  const months = Math.floor(days / 30);
  return months === 1 ? "hace 1 mes" : `hace ${months} meses`;
}

function statsSummary(stats: CatalogBackup["stats"]): string {
  if (!stats) return "";
  const obj = typeof stats === "string" ? safeParse(stats) : stats;
  if (!obj) return typeof stats === "string" ? stats : "";
  const parts: string[] = [];
  if (typeof obj.items_before === "number") parts.push(`${obj.items_before} ítems`);
  if (typeof obj.updated === "number") parts.push(`${obj.updated} actualizados`);
  if (typeof obj.new === "number") parts.push(`${obj.new} nuevos`);
  if (typeof obj.reason === "string") parts.push(obj.reason);
  return parts.join(" · ");
}

function safeParse(s: string): Record<string, unknown> | null {
  try {
    return JSON.parse(s) as Record<string, unknown>;
  } catch {
    return null;
  }
}

function deriveMeta(content: unknown): { count: number; lastUpdated: string | null } {
  const items = Array.isArray(content)
    ? content
    : content && typeof content === "object" && Array.isArray((content as { items?: unknown }).items)
      ? ((content as { items: unknown[] }).items)
      : [];
  const first = items[0] as { last_updated?: string } | undefined;
  return {
    count: Array.isArray(content) ? content.length : items.length || 1,
    lastUpdated: first?.last_updated ?? null,
  };
}

export function CatalogViewer({ name }: { name: string }) {
  const [content, setContent] = useState<unknown>(null);
  const [backups, setBackups] = useState<CatalogBackup[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [toast, setToast] = useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  const load = useCallback(async () => {
    const [c, b] = await Promise.all([getCatalog(name), listBackups(name)]);
    setContent(c);
    setBackups(b);
  }, [name]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await load();
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Error desconocido");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const handleRestore = async (id: number) => {
    setRestoring(true);
    try {
      await restoreBackup(id);
      setConfirmId(null);
      await load();
      setToast({ kind: "ok", msg: `Catálogo restaurado desde backup #${id}.` });
    } catch (err) {
      setConfirmId(null);
      setToast({ kind: "err", msg: err instanceof Error ? err.message : "Falló la restauración." });
    } finally {
      setRestoring(false);
    }
  };

  if (error) {
    return (
      <div data-testid="catalog-viewer-error" role="alert" style={{ color: "var(--error)" }}>
        No pude cargar el catálogo: {error}
      </div>
    );
  }

  if (content === null || backups === null) {
    return (
      <div data-testid="catalog-viewer-loading" style={{ color: "var(--ink-mute)" }}>
        Cargando catálogo…
      </div>
    );
  }

  const meta = deriveMeta(content);

  return (
    <div className="catalog-viewer">
      <div className="section-head">
        <h2 className="mono">{name}</h2>
        <span className="meta">
          {meta.count} ítems{meta.lastUpdated ? ` · última actualización ${meta.lastUpdated}` : ""}
        </span>
      </div>

      <div className="catalog-viewer-grid">
        <section className="catalog-json-pane">
          <h3>Contenido</h3>
          <pre className="catalog-json" data-testid="catalog-json">
            {JSON.stringify(content, null, 2)}
          </pre>
        </section>

        <aside className="catalog-backups-pane">
          <h3>Versiones anteriores</h3>
          {backups.length === 0 ? (
            <p data-testid="backup-list-empty" style={{ color: "var(--ink-mute)", fontSize: 13 }}>
              Sin backups todavía. Se generan automáticamente al importar o restaurar.
            </p>
          ) : (
            <ul className="backup-list" data-testid="backup-list">
              {backups.map((b) => (
                <li key={b.id} className="backup-row" data-testid={`backup-row-${b.id}`}>
                  <div className="backup-row-main">
                    <span className="backup-when">{formatRelative(b.created_at)}</span>
                    <span className="backup-source mono">{b.source_file ?? "—"}</span>
                  </div>
                  {statsSummary(b.stats) && (
                    <span className="backup-stats meta">{statsSummary(b.stats)}</span>
                  )}
                  <button
                    type="button"
                    className="btn ghost"
                    data-testid={`backup-restore-${b.id}`}
                    onClick={() => setConfirmId(b.id)}
                  >
                    Restaurar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>

      {confirmId !== null && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" data-testid="restore-confirm">
          <div className="modal-card">
            <h3>Restaurar backup #{confirmId}</h3>
            <p>
              Vas a reemplazar el contenido actual de <strong className="mono">{name}</strong> por el
              de este backup. Se genera un backup automático del estado actual antes de restaurar.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn ghost"
                onClick={() => setConfirmId(null)}
                disabled={restoring}
                data-testid="restore-cancel"
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn primary"
                onClick={() => handleRestore(confirmId)}
                disabled={restoring}
                data-testid="restore-confirm-yes"
              >
                {restoring ? "Restaurando…" : "Restaurar"}
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div
          className="catalog-toast"
          role="status"
          data-testid="catalog-toast"
          style={{ color: toast.kind === "ok" ? "var(--ok, #4ade80)" : "var(--error)" }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
