import React from "react";

interface Props {
  onClick: () => void;
  children: React.ReactNode;
  primary?: boolean;
  disabled?: boolean;
  title?: string;
}

function IconBtn({ onClick, children, primary, disabled, title }: Props) {
  return (
    <button onClick={onClick} disabled={disabled} title={title} style={{
      width: 32, height: 32, borderRadius: "50%",
      border: primary ? "none" : "1px solid var(--b1)",
      background: primary ? "var(--acc)" : "transparent",
      color: primary ? "#fff" : "var(--t2)",
      cursor: disabled ? "not-allowed" : "pointer",
      display: "flex", alignItems: "center", justifyContent: "center",
      transition: "all .1s", opacity: disabled ? 0.4 : 1,
    }}>
      {children}
    </button>
  );
}

export default React.memo(IconBtn);
