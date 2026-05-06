"use client";

/**
 * Stepper v2 — los 5 pasos del flow.
 *
 * Reusa clases legacy `.stepper`, `.step`, `.step.done`, `.step.now`
 * y `.n` de operator-shared.css.
 *
 * Sprint 2: usa `usePathname()` para detectar el paso actual de la
 * URL. NO interactivo — los `<div>` no son `<Link>` todavía. Click
 * handlers + navigation real vienen en sub-PRs siguientes.
 *
 * Lógica de estados (igual que `chrome.js` legacy):
 *   - paso < currentStep ⇒ `.done` (✓ verde)
 *   - paso === currentStep ⇒ `.now` (celeste, número visible)
 *   - paso > currentStep ⇒ pendiente (sin clase, número mute)
 */
import { usePathname } from "next/navigation";
import { STEPS, getCurrentStep, type StepId } from "@/lib/v2/mocks/canonicalQuote";

export function Stepper() {
  const pathname = usePathname() ?? "";
  const currentStep: StepId = getCurrentStep(pathname);
  const currentOrder = STEPS.find((s) => s.id === currentStep)?.order ?? 1;

  return (
    <nav className="stepper" data-current-step={currentStep}>
      {STEPS.map((step) => {
        const isDone = step.order < currentOrder;
        const isNow = step.order === currentOrder;
        const cls = ["step", isDone ? "done" : "", isNow ? "now" : ""].filter(Boolean).join(" ");
        return (
          <div key={step.id} className={cls} data-step={step.id}>
            <span className="n">{isDone ? "" : step.order}</span>
            <span>{step.label}</span>
          </div>
        );
      })}
    </nav>
  );
}
