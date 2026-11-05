import type React from 'react';

export function TradeTable({ title, count, variant, children }: {
  title: string; count: number; variant?: 'live' | 'scalp' | 'shadow'; children: React.ReactNode;
}) {
  return (
    <section className="surface-card trade-history border">
      <header className="trade-table-heading table-header border-b">
        <h2 className="section-title">{title}</h2>
        <span className="muted-text tabular-nums">{count} rows</span>
      </header>
      <div className="trade-table-scroll" role="region" aria-label={`${title} table`} tabIndex={0}>
        <table className={`trade-table ${variant ? `trade-table-${variant}` : ''}`}>
          <caption className="sr-only">{title}</caption>
          {children}
        </table>
      </div>
    </section>
  );
}
