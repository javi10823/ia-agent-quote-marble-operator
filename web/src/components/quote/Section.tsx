import React from "react";

interface Props {
  title: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}

export default function Section({ title, children, style: extraStyle }: Props) {
  return (
    <div style={{
      background: "var(--s1)", border: "1px solid var(--b1)",
      borderRadius: 12, padding: "18px 22px", ...extraStyle,
    }}>
      <div style={{
        fontSize: 13, fontWeight: 600, color: "var(--t1)",
        textTransform: "uppercase", letterSpacing: "0.06em",
        marginBottom: 14, paddingBottom: 8, borderBottom: "1px solid var(--b1)",
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}
