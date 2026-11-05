export function CountTable({ title, rows }: { title: string; rows: Record<string, number> }) {
  const entries = Object.entries(rows ?? {});

  return (
    <section className="surface-card border p-4">
      <h2 className="section-title mb-3 text-sm font-semibold uppercase tracking-wide">{title}</h2>
      <div className="grid gap-1.5">
        {entries.map(([name, count]) => (
          <div className="surface-soft flex items-center justify-between border px-3 py-2 text-sm" key={name}>
            <span>{name}</span>
            <span className="font-semibold tabular-nums">{count}</span>
          </div>
        ))}
        {!entries.length && (
          <div className="surface-soft muted-text border px-3 py-2 text-sm">No data yet</div>
        )}
      </div>
    </section>
  );
}
