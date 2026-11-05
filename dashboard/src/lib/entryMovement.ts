import type { TradeRow } from '../types/trades';

const value = (text?: string) => text?.trim() && Number.isFinite(Number(text)) ? Number(text) : null;

export function entryMovement(row: TradeRow) {
  let prices: number[] = [];
  try {
    const parsed: unknown = JSON.parse(row.entry_window_prices || 'null');
    if (Array.isArray(parsed) && parsed.every(item => value(String(item)) !== null && Number(item) > 0)) prices = parsed.map(Number).slice(-4);
  } catch { /* Older records do not contain a price window. */ }
  const current = value(row.entry_btc_price) ?? prices[prices.length - 1] ?? null;
  let previous = prices.length >= 2 ? prices[prices.length - 2] : null;
  let change = value(row.entry_btc_change_usd);
  const percent = value(row.entry_btc_change_pct);
  if (previous === null && current !== null && change !== null) previous = current - change;
  if (previous === null && current !== null && percent !== null && percent > -100) previous = current / (1 + percent / 100);
  if (change === null && current !== null && previous !== null) change = current - previous;
  const direction = ['UP', 'DOWN', 'FLAT'].includes(row.entry_direction) ? row.entry_direction : 'UNKNOWN';
  const matches = direction === 'UNKNOWN' || direction === 'FLAT' || !['YES', 'NO'].includes(row.side)
    ? null : direction === (row.side === 'YES' ? 'UP' : 'DOWN');
  return { current, previous, change, percent, prices, direction, matches,
    source: row.entry_direction_basis === 'RECORDED' ? 'Recorded' : row.entry_direction_basis === 'INFERRED' ? 'Inferred' : row.entry_direction_basis === 'AMBIGUOUS' ? 'Uncertain' : 'Unknown' };
}
