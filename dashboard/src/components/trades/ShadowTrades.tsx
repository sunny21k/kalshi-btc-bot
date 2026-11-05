import type { TradeRow } from '../../types/trades';
import { fmtDateTime, tableMoney } from '../../utils/format';
import { TradeTable } from './TradeTable';
import { TickerLabel } from './TickerLabel';

export function ShadowTrades({ rows }: { rows: TradeRow[] }) {
  const items = rows ?? [];

  return (
    <TradeTable title="Recent Blocked Signals" count={items.length} variant="shadow">
      <thead>
        <tr><th scope="col">Time</th><th scope="col">Ticker</th><th scope="col">Decision</th><th scope="col">Side</th><th scope="col" className="table-number">Price</th><th scope="col">Reason</th></tr>
      </thead>
      <tbody>
        {items.map((row, index) => (
          <tr key={`${row.ticker}-${row.reason}-${index}`}>
            <td className="table-time" title={row.timestamp}>{fmtDateTime(row.timestamp) || '--'}</td>
            <td><TickerLabel value={row.ticker} /></td>
            <td className="table-status">{row.decision || '--'}</td>
            <td className="table-side">{row.side || '--'}</td>
            <td className="table-number" title={row.entry_price || row.price}>{tableMoney(row.entry_price || row.price)}</td>
            <td><span className="table-reason muted-heading" title={row.reason}>{row.reason || '--'}</span></td>
          </tr>
        ))}
        {!items.length && (
          <tr>
            <td className="table-empty muted-text" colSpan={6}>No blocked signals yet</td>
          </tr>
        )}
      </tbody>
    </TradeTable>
  );
}
