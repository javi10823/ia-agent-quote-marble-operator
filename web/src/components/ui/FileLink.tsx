import React from "react";

interface Props {
  href: string;
  label: string;
  color: string;
}

function FileLink({ href, label, color }: Props) {
  const emoji = label === "PDF" ? "📄" : label === "Excel" ? "📊" : "☁";
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" style={{
      display: "flex", alignItems: "center", gap: 5,
      padding: "6px 12px", borderRadius: 6,
      fontSize: 11, fontWeight: 500, textDecoration: "none",
      border: `1px solid ${color}33`, background: "transparent", color,
    }}>
      {emoji} {label}
    </a>
  );
}

export default React.memo(FileLink);
