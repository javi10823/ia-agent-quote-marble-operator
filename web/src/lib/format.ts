export const fmtARS = (n: number | null | undefined) => {
  if (n == null || isNaN(n)) return "—";
  return `$${Math.round(n).toLocaleString("es-AR")}`;
};

export const fmtUSD = (n: number | null | undefined) => {
  if (n == null || isNaN(n)) return "—";
  return `USD ${Math.round(n).toLocaleString("es-AR")}`;
};

export const fmtQty = (n: number | null | undefined) => {
  if (n == null || isNaN(n)) return "—";
  if (Math.abs(n - Math.round(n)) < 0.05) return String(Math.round(n));
  return n.toFixed(2).replace(".", ",");
};
