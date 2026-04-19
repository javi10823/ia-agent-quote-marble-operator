import React from "react";

interface Props {
  title: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export default function Section({ title, children, style: extraStyle }: Props) {
  return (
    <div style={{
      background: "transparent", border: "none",
      padding: "6px 0 24px", ...extraStyle,
    }}>
      <div style={{
        fontFamily: "var(--font-serif), Georgia, serif",
        fontStyle: "italic",
        fontSize: 20, fontWeight: 500, color: "var(--t1)",
        letterSpacing: "-0.01em",
        marginBottom: 18, paddingBottom: 10, borderBottom: "1px solid var(--b1)",
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}
