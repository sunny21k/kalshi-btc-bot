import type { BucketStats } from '../../types/trades';
import { fmtPct, moneyClass, tableMoney } from '../../utils/format';

export function BucketTable({ title, buckets }: { title: string; buckets: BucketStats }) {
  const entries = Object.entries(buckets ?? {});

  return (
    <section className="surface-card border p-4">
      <h2 className="section-title mb-3 text-sm font-semibold uppercase tracking-wide">{title}</h2>
      <table className="w-full text-left text-sm">
        <thead className="muted-text text-xs">
          <tr><th className="pb-2">Bucket</th><th className="table-number pb-2">Trades</th><th className="table-number pb-2">Win</th><th className="table-number pb-2">P/L</th></tr>
        </thead>
        <tbody>
          {entries.map(([name, item]) => (
            <tr className="row-border border-t" key={name}>
              <td className="py-2">{name}</td>
              <td className="table-number">{item.total}</td>
              <td className="table-number">{fmtPct(item.winRate)}</td>
              <td className={`table-number ${moneyClass(item.profitLoss)}`}>{tableMoney(item.profitLoss, true)}</td>
            </tr>
          ))}
          {!entries.length && (
            <tr className="row-border border-t">
              <td className="muted-text py-3" colSpan={4}>No data yet</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
