import type { TradeRow } from '../../types/trades';
import { fmtDateTime, moneyClass, shortId, tableMoney } from '../../utils/format';
import { TradeTable } from './TradeTable';
import { TickerLabel } from './TickerLabel';

export function RecentTrades({ title, rows, live }: { title: string; rows: TradeRow[]; live?: boolean }) {
  const items = rows ?? [];

  return (
    <TradeTable title={title} count={items.length} variant={live ? 'live' : undefined}>
      <thead>
        <tr>
          <th scope="col">ID</th><th scope="col">Made</th><th scope="col">Ticker</th><th scope="col">Side</th><th scope="col" className="table-number">Entry</th>
          {live && <><th scope="col" className="table-number">Filled</th><th scope="col">Status</th><th scope="col" className="table-number">Fees</th></>}
          <th scope="col">Result</th><th scope="col" className="table-number">{live ? 'Net P/L' : 'P/L'}</th><th scope="col">Strategy</th>
        </tr>
      </thead>
      <tbody>
        {items.map((row, index) => (
          <tr key={`${row.trade_id || row.ticker}-${index}`}>
            <td className="table-id muted-text" title={row.trade_id}>{shortId(row.trade_id) || '--'}</td>
            <td className="table-time" title={row.timestamp}><time dateTime={row.timestamp}>{fmtDateTime(row.timestamp) || '--'}</time></td>
            <td><TickerLabel value={row.ticker} /></td>
            <td className="table-side">{row.side || '--'}</td>
            <td className="table-number" title={row.entry_price}>{tableMoney(row.entry_price)}</td>
            {live && <>
              <td className="table-number">{row.filled_count || '?'} / {row.submitted_count || row.contracts || '?'}</td>
              <td className={`table-status ${row.fill_status === 'REJECTED' ? 'money-negative' : row.fill_status === 'FILLED' ? 'money-positive' : 'muted-heading'}`} title={row.sync_error || row.error}>
                {row.fill_status === 'UNKNOWN' ? 'Unverified' : row.fill_status || '--'}
              </td>
              <td className="table-number" title={row.fees_paid}>{tableMoney(row.fees_paid)}</td>
            </>}
            <td className={row.actual_result ? 'table-side' : 'muted-text'}>{row.actual_result || '--'}</td>
            <td className={`table-number table-profit ${row.profit_loss ? moneyClass(row.profit_loss) : 'muted-text'}`} title={row.profit_loss}>
              {row.profit_loss ? tableMoney(row.profit_loss, true) : live ? row.fill_status === 'UNFILLED' ? 'No fill' : row.fill_status === 'REJECTED' ? '--' : 'Pending' : '--'}
            </td>
            <td><span className="table-strategy muted-heading" title={row.strategy_name}>{row.strategy_name || '--'}</span></td>
          </tr>
        ))}
        {!items.length && (
          <tr>
            <td className="table-empty muted-text" colSpan={live ? 11 : 8}>No trades yet</td>
          </tr>
        )}
      </tbody>
    </TradeTable>
  );
}
