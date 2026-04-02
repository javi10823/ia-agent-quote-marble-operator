import React from "react";

interface Props {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}

function TabBtn({ active, children, onClick, disabled }: Props) {
  return (
    <button onClick={disabled ? undefined : onClick} style={{
      padding: "10px 20px", fontSize: 13, fontWeight: 500,
      border: "none", borderBottom: active ? "2px solid var(--acc)" : "2px solid transparent",
      background: "transparent",
      color: disabled ? "var(--t4)" : active ? "var(--acc)" : "var(--t3)",
      cursor: disabled ? "default" : "pointer",
      fontFamily: "inherit",
      opacity: disabled ? 0.5 : 1,
    }}>
      {children}
    </button>
  );
}

export default React.memo(TabBtn);
