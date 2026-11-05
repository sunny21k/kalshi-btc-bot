import React from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

export function PopupCard({ title, subtitle, closeLabel, onClose, children }: {
  title: string; subtitle?: string; closeLabel: string; onClose: () => void; children: React.ReactNode;
}) {
  const card = React.useRef<HTMLElement>(null);
  const close = React.useRef(onClose);
  close.current = onClose;
  const titleId = React.useId();

  React.useEffect(() => {
    const previous = document.activeElement;
    card.current?.focus({ preventScroll: true });
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') close.current(); };
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !card.current?.contains(event.target)) close.current();
    };
    document.addEventListener('keydown', escape);
    document.addEventListener('pointerdown', outside);
    return () => {
      const restoreFocus = card.current?.contains(document.activeElement) || document.activeElement === document.body;
      document.removeEventListener('keydown', escape);
      document.removeEventListener('pointerdown', outside);
      if (restoreFocus && previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true });
    };
  }, []);

  const popup = (
    <div className="detail-popup-layer">
      <section ref={card} role="dialog" aria-labelledby={titleId} tabIndex={-1} className="trade-detail-dialog">
        <header className="trade-detail-header">
          <div><h2 id={titleId}>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
          <button type="button" aria-label={closeLabel} onClick={onClose}><X size={18} /></button>
        </header>
        <div className="trade-detail-body">{children}</div>
      </section>
    </div>
  );
  // Nonmodal cards intentionally leave background scrolling and focus available.
  return typeof document === 'undefined' ? popup : createPortal(popup, document.body);
}
