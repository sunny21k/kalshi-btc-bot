import type { TradeRow } from '../../types/trades';
import { fmtDateTime, moneyClass, shortId, tableMoney } from '../../utils/format';
import { TradeTable } from './TradeTable';

const eventClass = (event?: string) => event === 'OPEN' ? 'event-open' : event === 'CLOSE' ? 'event-close' : 'muted-text';
const eventRowClass = (event?: string) => event === 'OPEN' ? 'event-row-open' : event === 'CLOSE' ? 'event-row-close' : '';

export function ScalpTrades({ rows }: { rows: TradeRow[] }) {
  const items = rows ?? [];

  return (
    <TradeTable title="Recent Scalp Events" count={items.length} variant="scalp">
      <thead>
        <tr><th scope="col">ID</th><th scope="col">Event</th><th scope="col">Side</th><th scope="col">Opened</th><th scope="col">Sold</th><th scope="col" className="table-number">Entry</th><th scope="col" className="table-number">Exit</th><th scope="col" className="table-number">P/L</th><th scope="col">Reason</th></tr>
      </thead>
      <tbody>
        {items.map((row, index) => (
          <tr className={eventRowClass(row.event)} key={`${row.trade_id}-${row.event}-${index}`}>
            <td className="table-id muted-text" title={row.trade_id}>{shortId(row.trade_id) || '--'}</td>
            <td className={`table-status ${eventClass(row.event)}`}>{row.event}</td>
            <td className="table-side">{row.side}</td>
            <td className="table-time" title={row.opened_at || (row.event === 'OPEN' ? row.timestamp : '')}>{fmtDateTime(row.opened_at || (row.event === 'OPEN' ? row.timestamp : '')) || '--'}</td>
            <td className="table-time" title={row.closed_at || (row.event === 'CLOSE' ? row.timestamp : '')}>{fmtDateTime(row.closed_at || (row.event === 'CLOSE' ? row.timestamp : '')) || '--'}</td>
            <td className="table-number" title={row.entry_price}>{tableMoney(row.entry_price)}</td>
            <td className="table-number" title={row.exit_price}>{tableMoney(row.exit_price)}</td>
            <td className={`table-number table-profit ${row.profit_loss ? moneyClass(row.profit_loss) : 'muted-text'}`} title={row.profit_loss}>{tableMoney(row.profit_loss, true)}</td>
            <td><span className="table-reason muted-heading" title={row.reason}>{row.reason || '--'}</span></td>
          </tr>
        ))}
        {!items.length && (
          <tr>
            <td className="table-empty muted-text" colSpan={9}>No scalp events yet</td>
          </tr>
        )}
      </tbody>
    </TradeTable>
  );
}
