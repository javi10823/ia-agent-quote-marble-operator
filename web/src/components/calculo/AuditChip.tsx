/**
 * Chip `.aud-i` con tooltip nativo (title) · Sprint 3 paso-4.
 */
export function AuditChip({ title }: { title: string }) {
  return (
    <span className="aud-i" title={title} aria-label={title}>
      ⓘ
    </span>
  );
}
