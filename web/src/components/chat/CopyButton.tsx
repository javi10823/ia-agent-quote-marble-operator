"use client";
import { useState } from "react";
import clsx from "clsx";

interface Props {
  text: string;
  label?: string;
  iconOnly?: boolean;
  fullWidth?: boolean;
  className?: string;
}

export default function CopyButton({
  text,
  label = "Copiar",
  iconOnly = false,
  fullWidth = false,
  className,
}: Props) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const done = () => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    };
    try {
      await navigator.clipboard.writeText(text);
      done();
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.top = "0";
      ta.style.left = "0";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      try {
        document.execCommand("copy");
        done();
      } catch {
        /* ignore */
      }
      document.body.removeChild(ta);
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      title={iconOnly ? label : undefined}
      aria-label={label}
      className={clsx(
        "relative z-20 inline-flex items-center gap-1.5 rounded-md text-[11px] font-medium transition-colors cursor-pointer",
        "text-t3 bg-transparent border border-b2",
        "hover:text-acc hover:bg-acc2 hover:border-acc/40",
        iconOnly
          ? "p-1.5 min-w-[44px] min-h-[44px] justify-center"
          : "px-2.5 py-1.5",
        fullWidth && "w-full justify-center min-h-[44px]",
        className,
      )}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        className={clsx("shrink-0", fullWidth ? "w-3.5 h-3.5" : "w-3 h-3")}
      >
        <path d="M8 5h8a2 2 0 012 2v12a2 2 0 01-2 2H8a2 2 0 01-2-2V7a2 2 0 012-2z" />
        <path d="M16 3H10a2 2 0 00-2 2" />
      </svg>
      {!iconOnly && <span>{label}</span>}
      <span
        className={clsx(
          "absolute top-full mt-1.5 right-0 px-2.5 py-1 rounded-md bg-grn text-white text-[11px] font-semibold pointer-events-none transition-opacity duration-200 whitespace-nowrap z-20",
          copied ? "opacity-100" : "opacity-0",
        )}
      >
        Copiado ✓
      </span>
    </button>
  );
}
