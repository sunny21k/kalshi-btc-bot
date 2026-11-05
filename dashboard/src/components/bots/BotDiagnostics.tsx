import { Activity } from 'lucide-react';
import type { BotRuntime } from '../../types/bots';

const dateTime = (value?: string) => value ? new Date(value).toLocaleString() : 'No update yet';
const age = (seconds?: number | null) => seconds === null || seconds === undefined ? 'No update yet'
  : seconds < 1 ? 'Just now' : seconds < 60 ? `${Math.floor(seconds)}s ago`
  : seconds < 3600 ? `${Math.floor(seconds / 60)}m ago` : `${Math.floor(seconds / 3600)}h ago`;
const dollars = (value?: string | null, signed = false) => {
  if (value === undefined || value === null || value === '' || !Number.isFinite(Number(value))) return '--';
  return Number(value).toLocaleString('en-US', { style: 'currency', currency: 'USD', signDisplay: signed ? 'exceptZero' : 'auto' });
};
const cents = (value?: string | null) => value === undefined || value === null || value === '' ? '--' : `${(Number(value) * 100).toFixed(1)}c`;

export function BotDiagnostics({ runtime }: { runtime?: BotRuntime }) {
  if (!runtime) return (
    <section className="bot-diagnostics" aria-label="Bot diagnostics">
      <p className="muted-text text-xs">Restart the dashboard server and bot to enable entry reasons and health updates.</p>
    </section>
  );
  const market = runtime.market;
  const decision = runtime.decision;
  const historical = !runtime.processAlive || runtime.state === 'stale';
  const seconds = market?.closeAt && !historical
    ? Math.max(0, (new Date(market.closeAt).getTime() - Date.now()) / 1000)
    : market?.secondsRemaining !== undefined && market.secondsRemaining !== null ? Math.max(0, Number(market.secondsRemaining)) : null;
  const timeLeft = seconds !== null && Number.isFinite(seconds) ? `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s` : '--';
  const health = { healthy: 'Receiving updates', degraded: 'Needs attention', stale: 'Updates stale', starting: 'Awaiting heartbeat', stopped: 'Stopped' }[runtime.state];
  const error = runtime.lastApiError;
  const emptyHealth = !runtime.processAlive && !runtime.heartbeatAt && !runtime.price && !error && !runtime.lastError;
  const capReached = runtime.dailyLimit !== null && runtime.dailyLimit !== undefined && runtime.dailyLimit > 0
    && runtime.dailyAttempts !== null && runtime.dailyAttempts !== undefined && runtime.dailyAttempts >= runtime.dailyLimit;
  const blocked = runtime.blockers.length > 0;
  const outcome = decision?.action === 'HOLD' || decision?.action === 'OPEN' ? 'Managing open position'
    : decision?.action === 'SUBMITTED' ? 'Order attempted'
    : decision?.action === 'RECORDED' ? 'Paper entry recorded'
    : decision?.action === 'CLOSED' ? 'Position closed'
    : decision?.action?.startsWith('BUY') ? 'Entry signal detected' : 'Watching for an entry';
  return (
    <section className="bot-diagnostics" aria-label="Bot diagnostics">
      <div className="diagnostic-column">
        <div className="diagnostic-heading">
          <h3>Why no trade?</h3>
          {decision?.at && <span className="muted-text" title={dateTime(decision.at)}>Last decision {new Date(decision.at).toLocaleTimeString()}</span>}
        </div>
        {blocked ? <ul className="diagnostic-reasons">{runtime.blockers.map((reason) => <li key={reason}>{reason}</li>)}</ul>
          : <div className="diagnostic-outcome"><strong>{outcome}</strong><p className="muted-heading">{decision?.reason || 'Waiting for the first market evaluation.'}</p></div>}
        {market?.ticker && <>
          <div className="diagnostic-market muted-text" title={market.ticker}>
            {historical ? 'Last observed' : 'Market'} <span>{market.ticker}</span>
            {decision?.strategy && <span>{decision.strategy}</span>}
          </div>
          <dl className="diagnostic-context">
            <div><dt>{historical ? 'Time at sample' : 'Time left'}</dt><dd>{timeLeft}</dd></div>
            <div><dt>BTC vs target</dt><dd>{dollars(market.priceDifference, true)}</dd></div>
            <div><dt>Spread</dt><dd>{cents(market.spread)}</dd></div>
            <div><dt>YES / NO ask</dt><dd>{cents(market.yesAsk)} / {cents(market.noAsk)}</dd></div>
          </dl>
        </>}
        {runtime.dailyLimit !== null && runtime.dailyLimit !== undefined && <div className={`diagnostic-limit muted-text ${capReached ? 'diagnostic-limit-reached' : ''}`}>
          <div className="diagnostic-limit-heading"><span>Shared live attempts today <span className="diagnostic-timezone">UTC</span></span><strong>{runtime.dailyAttempts ?? 'Unverified'} / {runtime.dailyLimit === 0 ? 'No cap' : runtime.dailyLimit}</strong></div>
          {runtime.dailyLimit > 0 && runtime.dailyAttempts !== null && runtime.dailyAttempts !== undefined && <div
            className="diagnostic-limit-track" role="meter" aria-label="Shared daily live attempts"
            aria-valuemin={0} aria-valuemax={runtime.dailyLimit} aria-valuenow={Math.min(runtime.dailyAttempts, runtime.dailyLimit)}
            aria-valuetext={`${runtime.dailyAttempts} of ${runtime.dailyLimit} attempts`}
          ><span style={{ width: `${Math.min(100, Math.max(0, runtime.dailyAttempts / runtime.dailyLimit * 100))}%` }} /></div>}
        </div>}
      </div>
      <div className="diagnostic-column diagnostic-health">
        <div className="diagnostic-heading"><h3><Activity size={14} /> Bot health</h3><span className={runtime.state === 'healthy' ? 'money-positive' : runtime.state === 'stale' || runtime.state === 'degraded' ? 'money-negative' : 'muted-text'}>{health}</span></div>
        {emptyHealth ? <p className="diagnostic-empty muted-text">Heartbeat and price updates appear after the bot starts.</p> : <>
          <dl className="diagnostic-context health-context">
            <div title={dateTime(runtime.heartbeatAt)}><dt>Last heartbeat</dt><dd>{age(runtime.heartbeatAgeSeconds)}</dd></div>
            <div title={dateTime(runtime.price?.at)}><dt>Last BTC price</dt><dd>{dollars(runtime.price?.value)}</dd><div className="diagnostic-price-age muted-text">{runtime.price ? `Received ${age(runtime.priceAgeSeconds).toLowerCase()}` : 'Awaiting price'}</div></div>
          </dl>
          {(runtime.pid || runtime.stage) && <p className="diagnostic-activity muted-text">
            {runtime.pid ? `${runtime.processAlive ? 'Process' : 'Last process'} ${runtime.pid}${runtime.managed ? '' : ' (terminal)'}` : ''}
            {runtime.pid && runtime.stage ? ' | ' : ''}{runtime.stage}
          </p>}
        </>}
        {error ? <details className="diagnostic-error" open={error.active}>
          <summary className={error.active ? 'money-negative' : 'muted-text'}>Last API error | {error.source} | {error.active ? 'Active' : 'Recovered'} <span title={dateTime(error.at)}>{new Date(error.at).toLocaleTimeString()}</span></summary>
          <p>{error.type}: {error.message}</p>
          {error.recoveredAt && <p className="muted-text">Recovered {dateTime(error.recoveredAt)}</p>}
        </details> : !emptyHealth && <p className="diagnostic-activity muted-text">{runtime.heartbeatAt ? 'API errors: none recorded for this run' : 'No API observations yet'}</p>}
        {runtime.lastError && runtime.lastError.at !== error?.at && <details className="diagnostic-error" open={runtime.lastError.active}>
          <summary className="muted-text">Last bot error | {runtime.lastError.source}</summary>
          <p>{runtime.lastError.type}: {runtime.lastError.message}</p>
        </details>}
      </div>
    </section>
  );
}
