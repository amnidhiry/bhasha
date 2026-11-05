import type { ComponentChildren } from "preact";
import { useEffect } from "preact/hooks";

export function Sheet({ open, onClose, label, children }: {
  open: boolean;
  onClose: () => void;
  label: string;
  children: ComponentChildren;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div class="sheet-backdrop" onClick={onClose}>
      <div class="sheet" role="dialog" aria-modal="true" aria-label={label} onClick={(e) => e.stopPropagation()}>
        <div class="sheet-grip" aria-hidden="true" />
        {children}
      </div>
    </div>
  );
}
