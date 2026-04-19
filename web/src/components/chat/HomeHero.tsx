"use client";

import { useMemo } from "react";
import { getCurrentUsername, prettyFirstName } from "@/lib/auth";

interface Props {
  /** Click en "Subir plano" — abre el file picker del composer. */
  onPickFile: () => void;
  /** Click en "Contame el enunciado" — foco en el textarea. */
  onFocusText: () => void;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Buen día";
  if (h < 19) return "Buenas tardes";
  return "Buenas noches";
}

/**
 * HomeHero — estado inicial del chat cuando todavía no hay mensajes.
 * Se muestra en `/quote/[id]` cuando el quote es nuevo (borrador sin
 * mensajes previos). Saludo dinámico + avatar piedra pulida + quick
 * actions que disparan composer y file picker.
 *
 * "Desde obra anterior" aparece deshabilitado — feature del backlog
 * (docs/BACKLOG.md) para clonar quote con otro material.
 */
export default function HomeHero({ onPickFile, onFocusText }: Props) {
  const name = useMemo(() => prettyFirstName(getCurrentUsername()), []);
  const greet = useMemo(() => greeting(), []);

  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 pb-20">
      <div className="w-full max-w-[620px]">
        {/* Avatar + greeting */}
        <div className="flex items-center gap-5 mb-4">
          <svg width="52" height="52" viewBox="0 0 40 40" className="shrink-0 block">
            <defs>
              <radialGradient id="hero-avatar" cx="35%" cy="30%" r="70%">
                <stop offset="0%" stopColor="oklch(0.85 0.06 200)" />
                <stop offset="55%" stopColor="var(--acc)" />
                <stop offset="100%" stopColor="oklch(0.38 0.06 220)" />
              </radialGradient>
            </defs>
            <circle cx="20" cy="20" r="18" fill="url(#hero-avatar)" />
            <ellipse cx="14" cy="14" rx="6" ry="3" fill="rgba(255,255,255,0.4)" />
            <ellipse cx="12" cy="12" rx="2" ry="1.2" fill="rgba(255,255,255,0.75)" />
          </svg>
          <h1 className="font-serif italic text-[38px] md:text-[44px] font-normal -tracking-[0.02em] text-t1 leading-[1.05]">
            {greet}{name ? "," : "."} {name && <span className="text-acc">{name}</span>}{name ? "." : ""}
          </h1>
        </div>

        <p className="text-[14px] text-t3 leading-[1.6] mb-8 max-w-[520px]">
          Arrastrame el plano o contame el trabajo. Te armo el análisis de
          contexto, mido los tramos y calculo el presupuesto — después lo
          validamos juntos.
        </p>

        {/* Quick actions */}
        <div className="flex flex-wrap gap-2">
          <QuickAction onClick={onPickFile} icon={<UploadIcon />} label="Subir plano" />
          <QuickAction onClick={onFocusText} icon={<PencilIcon />} label="Contame el enunciado" />
          <QuickAction disabled title="Próximamente — clonar una obra previa con otro material" icon={<CopyIcon />} label="Desde obra anterior" />
        </div>

        <div className="mt-10 text-[11px] text-t4 font-mono uppercase tracking-[0.14em]">
          Acepta PDF, JPG, PNG · hasta 10 MB
        </div>
      </div>
    </div>
  );
}

function QuickAction({ icon, label, onClick, disabled, title }: {
  icon: React.ReactNode; label: string;
  onClick?: () => void; disabled?: boolean; title?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={[
        "inline-flex items-center gap-2 px-4 py-2 rounded-full border text-[13px] font-medium font-sans transition",
        disabled
          ? "border-b1 bg-transparent text-t4 cursor-not-allowed"
          : "border-b1 bg-transparent text-t1 cursor-pointer hover:bg-white/[0.03] hover:border-b2",
      ].join(" ")}
    >
      <span className={disabled ? "text-t4" : "text-acc"}>{icon}</span>
      {label}
    </button>
  );
}

function UploadIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 16V4m0 0l-5 5m5-5l5 5M4 20h16"/></svg>;
}
function PencilIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>;
}
function CopyIcon() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/></svg>;
}
