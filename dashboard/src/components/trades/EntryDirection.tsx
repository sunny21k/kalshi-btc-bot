import type { TradeRow } from '../../types/trades';
import { fmtDateTime, tableMoney } from '../../utils/format';

export function EntryDirection({ row }: { row: TradeRow }) {
  if (row.fill_status === 'UNFILLED' || row.fill_status === 'REJECTED') return <span className="muted-text">No entry</span>;
  const known = ['UP', 'DOWN', 'FLAT'].includes(row.entry_direction);
  const basis = row.entry_direction_basis;
  if (!known) return <span className="muted-text" title={basis === 'AMBIGUOUS' ? 'Matching historical observations conflict; direction cannot be determined.' : 'No entry observation available. Run the trade direction audit to inspect historical logs.'}>{basis === 'AMBIGUOUS' ? 'Uncertain' : 'Unknown'}</span>;
  const tone = row.entry_direction_match === 'MATCH' ? 'money-positive' : row.entry_direction_match === 'OPPOSITE' ? 'money-negative' : 'muted-heading';
  const details = [
    basis === 'RECORDED' ? 'BTC observation saved with this entry/order decision.' : 'Inferred from matching shared-log observations; the exact bot source is unverified.',
    row.entry_direction_match === 'MATCH' ? 'Matches the bought side.' : row.entry_direction_match === 'OPPOSITE' ? 'Opposite to the bought side.' : 'BTC was flat.',
    row.entry_btc_change_usd && `Last BTC move: ${tableMoney(row.entry_btc_change_usd, true)}`,
    row.entry_btc_change_pct && `Last BTC change: ${row.entry_btc_change_pct}%`,
    row.entry_observed_at && `Observed: ${fmtDateTime(row.entry_observed_at)}`,
    row.entry_window_prices && `BTC prices used: ${row.entry_window_prices}`,
  ].filter(Boolean).join(' ');
  return <span className="inline-grid gap-0.5" title={details}><span className={tone}>{row.entry_direction === 'UP' ? 'BTC rising' : row.entry_direction === 'DOWN' ? 'BTC falling' : 'BTC flat'}</span><span className="muted-text text-[10px]">{basis === 'RECORDED' ? 'Recorded' : 'Inferred'}</span></span>;
}
