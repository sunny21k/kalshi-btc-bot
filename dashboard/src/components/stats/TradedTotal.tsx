export function TradedTotal({ value }: { value?: string }) {
  const amount = value === undefined ? 'N/A' : Number(value).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  return (
    <div className="row-border flex flex-wrap items-baseline justify-between gap-2 border-t px-3 py-2 text-sm">
      <span className="muted-heading">Total Traded</span>
      <span className="min-w-0 break-all font-semibold tabular-nums">{amount}</span>
    </div>
  );
}
