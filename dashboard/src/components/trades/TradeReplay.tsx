import React from 'react';
import { Pause, Play, RotateCcw, RefreshCw } from 'lucide-react';
import { fetchTradeReplay } from '../../api/dashboard';
import type { ReplayData, ReplayWindow } from '../../types/replay';
import { observationAt, relativeTime, replayBounds } from '../../lib/tradeReplay';
import { fmtDateTime } from '../../utils/format';
import { ReplayChart } from './ReplayChart';

export function TradeReplay({ botId, tradeId }: { botId: string; tradeId: string }) {
  const [data, setData] = React.useState<ReplayData | null>(null);
  const [error, setError] = React.useState('');
  const [progress, setProgress] = React.useState('Loading recorded observations…');
  const [refresh, setRefresh] = React.useState(0);
  const [cursor, setCursor] = React.useState(120);
  const [playing, setPlaying] = React.useState(false);
  const [speed, setSpeed] = React.useState(15);
  const [interval, setIntervalSeconds] = React.useState(15);
  const [window, setWindow] = React.useState<ReplayWindow>('market');
  const bounds = data ? replayBounds(data) : { min: -120, max: 120 };

  React.useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let force = refresh > 0;
    setError(''); setData(null); setPlaying(false);
    const load = async () => {
      try {
        const result = await fetchTradeReplay(botId, tradeId, force, controller.signal, window);
        force = false;
        if (controller.signal.aborted) return;
        if (result.status === 'preparing') {
          setProgress(`Preparing recorded prices… ${result.rows.toLocaleString()} observations checked.`);
          timer = setTimeout(load, 1200);
        } else {
          if (window === 'market' && result.window !== 'market') throw new Error('Restart the dashboard server to load full-market replay, or select the ±2-minute window.');
          setData(result); setCursor(replayBounds(result).max);
        }
      } catch (error) { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : 'Could not load replay.'); }
    };
    void load();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [botId, tradeId, refresh, window]);

  React.useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setCursor(value => Math.min(bounds.max, value + speed / 10)), 100);
    return () => clearInterval(timer);
  }, [playing, speed, bounds.max]);
  React.useEffect(() => { if (cursor >= bounds.max) setPlaying(false); }, [cursor, bounds.max]);

  const retry = <button type="button" className="surface-button replay-refresh" onClick={() => setRefresh(value => value + 1)}><RefreshCw size={13} /> Refresh data</button>;
  const windowControl = <label className="replay-window-control">Window <select aria-label="Replay window" value={window} onChange={event => setWindow(event.target.value as ReplayWindow)}><option value="market">Full 15-minute market</option><option value="entry">±2 minutes around entry</option></select></label>;
  if (error) return <section className="trade-replay">{windowControl}<p role="alert" className="money-negative">{error}</p>{retry}</section>;
  if (!data) return <section className="trade-replay">{windowControl}<p role="status" className="muted-text">{progress}</p></section>;
  const cursorTime = data.entry.at * 1000 + cursor * 1000;
  const point = observationAt(data.points, cursorTime);
  const age = point ? Math.max(0, (cursorTime - point.time) / 1000) : null;
  const dollars = (value: number | null | undefined) => value === null || value === undefined ? '--' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
  const cents = (value: number | null | undefined) => value === null || value === undefined ? '--' : `${(value * 100).toFixed(1)}¢`;
  const bid = data.entry.side === 'YES' ? point?.yesBid : point?.noBid;
  const ask = data.entry.side === 'YES' ? point?.yesAsk : point?.noAsk;
  const seek = (value: number) => { setPlaying(false); setCursor(Math.max(bounds.min, Math.min(bounds.max, value))); };
  return <section className="trade-replay" aria-label="Trade replay">
    <div className="replay-window-row">{windowControl}{retry}</div>
    <div className="replay-summary"><div><h3>{data.window === 'market' ? 'Full 15-minute market' : 'Entry replay · ±2 minutes'}</h3><p>{data.window === 'market' ? `${fmtDateTime(new Date(data.startTime).toISOString())} → ${fmtDateTime(new Date(data.endTime).toISOString())} · New York` : fmtDateTime(data.entry.timestamp)} · {data.sourceBasis === 'recorded' ? 'Recorded by this bot' : 'Reconstructed from shared logs'}</p></div></div>
    {data.points.length > 0 && <>
      <div className="replay-controls">
        <button type="button" className="surface-button" onClick={() => { if (cursor >= bounds.max) setCursor(bounds.min); setPlaying(value => !value); }}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? 'Pause' : 'Play'}</button>
        <button type="button" className="surface-button" disabled={bounds.min > 0 || bounds.max < 0} onClick={() => seek(0)}><RotateCcw size={13} /> At entry</button>
        <label>Speed <select value={speed} onChange={event => setSpeed(Number(event.target.value))}>{[1, 5, 15, 30, 60].map(value => <option key={value} value={value}>{value}×</option>)}</select></label>
        <label>Candles <select value={interval} onChange={event => setIntervalSeconds(Number(event.target.value))}>{[5, 15, 60].map(value => <option key={value} value={value}>{value === 60 ? '1 min' : `${value}s`}</option>)}</select></label>
      </div>
      <ReplayChart data={data} cursorSeconds={cursor} interval={interval} onSeek={seek} />
      <div className="replay-timeline"><input type="range" min={bounds.min} max={bounds.max} step=".1" value={cursor} onChange={event => seek(Number(event.target.value))} aria-label="Replay time relative to entry" aria-valuetext={`${relativeTime(cursor)} from entry`} /><output>{relativeTime(cursor)}</output></div>
      <p className="replay-observed-at muted-text">{point ? `Observation ${fmtDateTime(point.timestamp)} · ${age!.toFixed(1)}s before cursor` : 'No earlier observation is available at this cursor.'}</p>
      <dl className="replay-facts">
        <div><dt>BTC</dt><dd>{dollars(point?.btcPrice)}</dd></div>
        <div><dt>Target {data.targetBasis === 'inferred' ? '· inferred' : ''}</dt><dd>{dollars(point?.targetPrice)}</dd></div>
        <div><dt>BTC vs target</dt><dd>{point?.priceDifference === null || point?.priceDifference === undefined ? '--' : `${point.priceDifference >= 0 ? '+' : '−'}${dollars(Math.abs(point.priceDifference))}`}</dd></div>
        <div><dt>Countdown at sample</dt><dd>{point?.secondsRemaining === null || point?.secondsRemaining === undefined ? '--' : `${Math.floor(Math.max(0, point.secondsRemaining) / 60)}m ${Math.floor(Math.max(0, point.secondsRemaining) % 60)}s`}</dd></div>
        <div><dt>{data.entry.side} bid / ask</dt><dd>{cents(bid)} / {cents(ask)}</dd></div>
        <div><dt>Quoted spread</dt><dd>{bid == null || ask == null ? '--' : cents(ask - bid)}</dd></div>
      </dl>
      <div className="replay-decision"><span>{point?.decision || 'No decision recorded'}</span><p>{point?.reason || 'This sample has no matching bot-decision record.'}</p>{point?.strategy && <small>{point.strategy}</small>}</div>
    </>}
    <div className="replay-quality"><p>{data.coverage.samples} samples{data.coverage.typicalSeconds ? ` · typical spacing ${data.coverage.typicalSeconds}s` : ''} · shaded areas have missing observations</p><ul>{data.notes.map(note => <li key={note}>{note}</li>)}</ul></div>
  </section>;
}
