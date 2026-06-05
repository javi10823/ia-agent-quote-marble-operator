/**
 * Sección reusable del PdfSidebar · label + control + helper opcional.
 * Reusa `.ps-section`, `.lbl`, `.lbl-sub`, `.helper`, `.helper.todo`.
 */
"use client";

import type { ReactNode } from "react";

interface Props {
  label: string;
  labelSub?: string;
  helper?: string;
  helperTodo?: string;
  testId?: string;
  children: ReactNode;
}

export function PdfSidebarSection({
  label,
  labelSub,
  helper,
  helperTodo,
  testId,
  children,
}: Props) {
  return (
    <div className="ps-section" data-testid={testId}>
      <div className="lbl">
        {label}
        {labelSub && <span className="lbl-sub"> {labelSub}</span>}
      </div>
      {children}
      {helper && <div className="helper">{helper}</div>}
      {helperTodo && <div className="helper todo">{helperTodo}</div>}
    </div>
  );
}
