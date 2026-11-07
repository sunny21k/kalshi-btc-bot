import React from 'react';
import type { ReplayData } from '../../types/replay';
import { sampledCandles, quotePath, replayCursorAt, replayTicks } from '../../lib/tradeReplay';

export function ReplayChart({ data, cursorSeconds, interval, onSeek }: {
  data: ReplayData; cursorSeconds: number; interval: number; onSeek: (seconds: number) => void;
}) {
  const clip = React.useId();
  const [hover, setHover] = React.useState<number | null>(null);
  const width = 650, height = 270, left = 66, right = 14, top = 24, bottom = 30;
  const cursor = data.entry.at * 1000 + cursorSeconds * 1000;
  const candles = sampledCandles(data.points, interval, data.startTime, data.endTime, cursor);
  const prices = candles.flatMap(candle => [candle.high, candle.low]);
  if (data.targetPrice !== null && prices.length) prices.push(data.targetPrice);
  const minimum = prices.length ? Math.min(...prices) : 0;
  const maximum = prices.length ? Math.max(...prices) : 1;
  const padding = Math.max((maximum - minimum) * .1, .5);
  const low = minimum - padding, high = maximum + padding;
  const x = (time: number) => left + (time - data.startTime) / (data.endTime - data.startTime) * (width - left - right);
  const y = (price: number) => top + (high - price) / (high - low) * (height - top - bottom);
  const candleWidth = Math.max(2, (interval * 1000 / (data.endTime - data.startTime)) * (width - left - right) * .58);
  const entryX = x(data.entry.at * 1000);
  const entryVisible = data.entry.at * 1000 >= data.startTime && data.entry.at * 1000 <= data.endTime;
  const selected = hover === null ? null : candles.find(candle => candle.time === hover);
  const seek = (event: React.MouseEvent<SVGSVGElement>) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    onSeek(replayCursorAt(data, ((event.clientX - bounds.left) / bounds.width * width - left) / (width - left - right)));
  };
  const bidField = data.entry.side === 'YES' ? 'yesBid' : 'noBid';
  const askField = data.entry.side === 'YES' ? 'yesAsk' : 'noAsk';
  const quoteY = (value: number) => 16 + (1 - value) * 72;
  const gapMs = Math.min(30000, Math.max(15000, (data.coverage.typicalSeconds || 5) * 2500));
  return <div className="trade-replay-charts">
    <div className="replay-chart-title"><h4>BTC · sampled {interval}s candles</h4><span>{selected ? `O ${selected.open.toFixed(2)} H ${selected.high.toFixed(2)} L ${selected.low.toFixed(2)} C ${selected.close.toFixed(2)} · ${selected.count} samples` : data.targetPrice !== null ? `Dashed target: $${data.targetPrice.toFixed(2)}${data.targetBasis === 'inferred' ? ' · inferred' : ''}` : 'Click the chart or use the timeline to seek'}</span></div>
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={data.window === 'market' ? 'Sampled BTC candle replay of the full 15-minute market, New York time' : 'Sampled BTC candle replay, two minutes before and after entry'} onClick={seek} className="replay-candle-chart">
      <defs><clipPath id={clip}><rect x={left} y={top} width={width - left - right} height={height - top - bottom} /></clipPath></defs>
      {[0, 1, 2, 3].map(index => { const value = low + (high - low) * index / 3; return <g key={index}><line x1={left} x2={width - right} y1={y(value)} y2={y(value)} className="replay-grid" /><text x={left - 8} y={y(value) + 4} textAnchor="end" className="replay-axis">{prices.length ? value.toLocaleString('en-US', { maximumFractionDigits: 2 }) : '--'}</text></g>; })}
      <g clipPath={`url(#${clip})`}>
        {data.coverage.gaps.map((gap, index) => <rect key={index} x={x(gap.start)} width={Math.max(0, x(gap.end) - x(gap.start))} y={top} height={height - top - bottom} className="replay-gap" />)}
        {data.targetPrice !== null && prices.length > 0 && <line x1={left} x2={width - right} y1={y(data.targetPrice)} y2={y(data.targetPrice)} className="replay-target" />}
        {candles.map(candle => { const center = x(candle.time + interval * 500); return <g key={candle.time} className={candle.close > candle.open ? 'replay-candle-up' : candle.close < candle.open ? 'replay-candle-down' : 'replay-candle-flat'} onMouseEnter={() => setHover(candle.time)} onMouseLeave={() => setHover(null)}>
          <title>{`${new Date(candle.time).toISOString()} · sampled open ${candle.open}, high ${candle.high}, low ${candle.low}, close ${candle.close}; ${candle.count} observations`}</title>
          <line x1={center} x2={center} y1={y(candle.high)} y2={y(candle.low)} />
          <rect x={center - candleWidth / 2} width={candleWidth} y={Math.min(y(candle.open), y(candle.close))} height={Math.max(1.5, Math.abs(y(candle.open) - y(candle.close)))} />
        </g>; })}
        {entryVisible && <line x1={entryX} x2={entryX} y1={top} y2={height - bottom} className="replay-entry-line" />}
        <line x1={x(cursor)} x2={x(cursor)} y1={top} y2={height - bottom} className="replay-cursor-line" />
      </g>
      {entryVisible && <text x={entryX + (entryX > width - 135 ? -6 : 6)} textAnchor={entryX > width - 135 ? 'end' : 'start'} y={16} className="replay-entry-label">{data.entry.anchorLabel}{!data.entry.filled ? ' · unfilled' : ''}</text>}
      {replayTicks(data).map(tick => <text key={tick.time} x={x(tick.time)} y={height - 8} textAnchor="middle" className="replay-axis">{tick.label}</text>)}
      {!candles.length && <text x={width / 2} y={height / 2} textAnchor="middle" className="replay-axis">No BTC observations revealed at this time</text>}
    </svg>
    <div className="replay-chart-title replay-quote-heading"><h4>{data.entry.side} contract</h4><span><i className="replay-bid-key" /> Bid <i className="replay-ask-key" /> Ask · quoted, not fills</span></div>
    <svg viewBox={`0 0 ${width} 110`} role="img" aria-label={`${data.entry.side} recorded bid and ask replay`} className="replay-quote-chart">
      {[0, .5, 1].map(value => <g key={value}><line x1={left} x2={width - right} y1={quoteY(value)} y2={quoteY(value)} className="replay-grid" /><text x={left - 8} y={quoteY(value) + 4} textAnchor="end" className="replay-axis">{value * 100}¢</text></g>)}
      <path d={quotePath(data.points, bidField, cursor, x, quoteY, gapMs)} className="replay-bid-line" />
      <path d={quotePath(data.points, askField, cursor, x, quoteY, gapMs)} className="replay-ask-line" />
      {data.entry.entryPrice !== null && <line x1={left} x2={width - right} y1={quoteY(data.entry.entryPrice)} y2={quoteY(data.entry.entryPrice)} className="replay-limit-line" />}
      {entryVisible && <line x1={entryX} x2={entryX} y1={10} y2={90} className="replay-entry-line" />}
      <line x1={x(cursor)} x2={x(cursor)} y1={10} y2={90} className="replay-cursor-line" />
    </svg>
  </div>;
}
