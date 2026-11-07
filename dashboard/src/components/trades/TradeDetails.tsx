import React from 'react';
import type { TradeRow } from '../../types/trades';
import { entryMovement } from '../../lib/entryMovement';
import { fmtDateTime, tableMoney } from '../../utils/format';
import { PopupCard } from '../layout/PopupCard';
const TradeReplay = React.lazy(() => import('./TradeReplay').then(module => ({ default: module.TradeReplay })));

export function TradeDetails({ row, live = false, botId, onClose }: { row: TradeRow; live?: boolean; botId?: string; onClose: () => void }) {
  const [view, setView] = React.useState<'details' | 'replay'>('details');
  const replayBot = botId || row.bot_id;
  const movement = entryMovement(row);
  const dollars = (amount: number | null, signed = false) => amount === null ? '--' : tableMoney(String(amount), signed);
  const detail = (label: string, content: React.ReactNode) => <div key={label}><dt>{label}</dt><dd>{content || '--'}</dd></div>;
  const direction = movement.direction === 'UP' ? 'rising' : movement.direction === 'DOWN' ? 'falling' : movement.direction === 'FLAT' ? 'unchanged' : 'unknown';
  const hasFill = !live || Number(row.filled_count) > 0;
  return (
    <PopupCard title={live ? 'Live order details' : row.event ? 'Scalp trade details' : 'Paper trade details'}
      subtitle={row.ticker} closeLabel="Close trade details" onClose={onClose}>
        <div className="trade-detail-tabs" aria-label="Trade detail views">
          <button type="button" aria-pressed={view === 'details'} onClick={() => setView('details')}>Details</button>
          <button type="button" aria-pressed={view === 'replay'} disabled={!replayBot || !row.trade_id}
            title={!replayBot || !row.trade_id ? 'A bot and saved trade ID are required for replay' : 'Replay the full market or two minutes around entry'} onClick={() => setView('replay')}>Replay</button>
        </div>
        {view === 'replay' && replayBot ? <React.Suspense fallback={<p role="status" className="muted-text">Loading replay…</p>}><TradeReplay botId={replayBot} tradeId={row.trade_id} /></React.Suspense> : <>
        <dl className="trade-detail-facts">
          {detail(hasFill ? 'Purchased side' : 'Requested side', row.side)}
          {detail('Entry price', tableMoney(row.entry_price))}
          {detail('Contracts', live ? `${row.filled_count || '?'} filled / ${row.submitted_count || row.contracts || '?'} requested` : row.contracts)}
          {detail('Made', fmtDateTime(row.opened_at || row.timestamp))}
          {detail(live ? 'Actual fill cost' : 'Entry cost', tableMoney(live ? row.fill_cost : row.cost))}
          {live && detail('Actual fees', tableMoney(row.fees_paid))}
          {detail(live ? 'Net P/L' : 'P/L', row.profit_loss ? tableMoney(row.profit_loss, true) : live && !hasFill ? 'No confirmed fill' : 'Pending')}
          {detail('Market result', row.actual_result || 'Pending')}
          {detail(row.event ? 'Reason' : 'Strategy', row.strategy_name || row.reason)}
          {live && detail('Fill status', row.fill_status || 'Unverified')}
          {row.exit_price && detail('Exit price', tableMoney(row.exit_price))}
          {row.closed_at && detail('Sold', fmtDateTime(row.closed_at))}
        </dl>
        <section className="trade-detail-movement" aria-label="BTC movement details">
          <div className="trade-detail-section-heading"><h3>{live ? 'BTC at order decision' : 'BTC at entry'}</h3><span>{movement.source}</span></div>
          <p className="trade-detail-direction">{direction === 'unknown' ? 'BTC movement is unknown' : `BTC ${movement.source === 'Inferred' ? 'appears to have been' : 'was'} ${direction}`}</p>
          <p className="trade-detail-explanation">Rising means BTC’s price increased; falling means BTC’s price decreased. The purchased YES/NO side and final market result are shown separately.</p>
          {movement.source === 'Inferred' && <p className="trade-detail-source-note">Estimated from a matching historical log observation. Shared logs do not identify the exact bot source. The previous price and dollar move below are reconstructed from the saved BTC price and percentage change.</p>}
          {movement.source === 'Recorded' && <p className="trade-detail-source-note">Saved with this {live ? 'order attempt' : 'paper entry'} from the BTC observations used by the bot.</p>}
          {live && <p className="trade-detail-source-note">These observations describe the order decision. BTC at the exact exchange fill time was not recorded.</p>}
          {movement.source === 'Uncertain' && <p className="trade-detail-source-note">Matching historical observations disagree, so movement cannot be determined.</p>}
          {movement.source === 'Unknown' && <p className="trade-detail-source-note">No BTC observation is available for this entry. A prediction or market outcome cannot establish its earlier price movement.</p>}
          <dl className="trade-detail-facts trade-detail-price-facts">
            {detail('BTC observed', dollars(movement.current))}
            {detail(movement.source === 'Inferred' ? 'Inferred previous BTC' : 'Previous BTC price', dollars(movement.previous))}
            {detail(movement.source === 'Inferred' ? 'Inferred last move' : 'Last observed move', dollars(movement.change, true))}
            {detail('BTC change', movement.percent === null ? '--' : `${movement.percent > 0 ? '+' : ''}${movement.percent.toFixed(4)}%`)}
            {detail('Observed at', fmtDateTime(row.entry_observed_at))}
            {detail('Movement versus side', movement.matches === null ? '--' : movement.matches ? `Matches ${row.side}` : `Opposite to ${row.side}`)}
          </dl>
          {!!movement.prices.length && <div className="trade-detail-price-window"><h4>Saved BTC prices · oldest to newest</h4><ol>{movement.prices.map((price, index) => <li key={index}><span>Price {index + 1}</span><strong>{dollars(price)}</strong>{index > 0 && <small>{dollars(price - movement.prices[index - 1], true)}</small>}</li>)}</ol></div>}
        </section>
        <div className="trade-detail-identifiers"><div><span>Trade ID</span><code>{row.trade_id || '--'}</code></div>{live && row.order_id && <div><span>Exchange order ID</span><code>{row.order_id}</code></div>}</div>
        {(row.sync_error || row.error) && <p className="money-negative trade-detail-error">{row.sync_error || row.error}</p>}
        </>}
    </PopupCard>
  );
}
