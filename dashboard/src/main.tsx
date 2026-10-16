import React from 'react';
import ReactDOM from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  Bot,
  CircleDollarSign,
  Gauge,
  Menu,
  Moon,
  Play,
  RefreshCw,
  Sun,
  Square,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import './styles.css';

type SideStats = {
  total: number;
  settled: number;
  winRate: number | null;
  profitLoss: string;
};

type TradeRow = Record<string, string>;
type BucketStats = Record<string, SideStats>;

type TradeStats = {
  total: number;
  settled: number;
  unsettled: number;
  wins: number;
  losses: number;
  winRate: number | null;
  totalInvested: string;
  profitLoss: string;
  roi: number | null;
  yes: SideStats;
  no: SideStats;
  byStrategy: BucketStats;
  byTime: BucketStats;
  recent: TradeRow[];
};

type ShadowStats = {
  total: number;
  decisions: Record<string, number>;
  blockedReasons: Record<string, number>;
  recent: TradeRow[];
};

type ScalpStats = {
  total: number;
  closed: number;
  open: number;
  wins: number;
  losses: number;
  winRate: number | null;
  totalInvested: string;
  profitLoss: string;
  peakProfit: string;
  byReason: Record<string, number>;
  recent: TradeRow[];
};

type DashboardStats = {
  paper: TradeStats;
  live: TradeStats;
  scalp: ScalpStats;
  shadow: ShadowStats;
  bots: BotStatus[];
};

type BotStatus = {
  id: string;
  name: string;
  mode: string;
  description: string;
  running: boolean;
  pid: number | null;
  returnCode: number | null;
  logFile: string;
};

const moneyClass = (value: string) => Number(value || 0) >= 0 ? 'money-positive' : 'money-negative';
const fmtPct = (value: number | null) => value === null ? 'N/A' : `${value.toFixed(2)}%`;
const shortId = (value?: string) => value ? value.replace(/^paper-|^live-|^scalp-/, '').slice(0, 8) : '';
const fmtDateTime = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};
const eventClass = (event?: string) => event === 'OPEN' ? 'event-open' : event === 'CLOSE' ? 'event-close' : 'muted-text';
const eventRowClass = (event?: string) => event === 'OPEN' ? 'event-row-open' : event === 'CLOSE' ? 'event-row-close' : '';
type TabId = 'btc15_paper' | 'btc15_live' | 'scalp_paper' | 'shadow';

const emptyScalp: ScalpStats = {
  total: 0,
  closed: 0,
  open: 0,
  wins: 0,
  losses: 0,
  winRate: null,
  totalInvested: '0.0000',
  profitLoss: '0.0000',
  peakProfit: '0.0000',
  byReason: {},
  recent: [],
};

function Metric({ label, value, tone, large }: { label: string; value: React.ReactNode; tone?: string; large?: boolean }) {
  return (
    <div className="surface-card metric-box border px-3 py-2">
      <div className="muted-text text-xs font-medium uppercase tracking-wide">{label}</div>
      <div className={`mt-0.5 font-semibold tabular-nums ${large ? 'text-xl' : 'text-base'} ${tone ?? ''}`}>{value}</div>
    </div>
  );
}

function SideCard({ label, stats, icon }: { label: string; stats: SideStats; icon: React.ReactNode }) {
  return (
    <div className="surface-card border p-3">
      <div className="muted-heading mb-2 flex items-center gap-2 text-sm font-medium">{icon}{label}</div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <div><div className="muted-text text-xs">Trades</div><div className="font-semibold">{stats.total}</div></div>
        <div><div className="muted-text text-xs">Win Rate</div><div className="font-semibold">{fmtPct(stats.winRate)}</div></div>
        <div><div className="muted-text text-xs">P/L</div><div className={`font-semibold ${moneyClass(stats.profitLoss)}`}>${stats.profitLoss}</div></div>
      </div>
    </div>
  );
}

function TradePanel({ title, stats, live }: { title: string; stats: TradeStats; live?: boolean }) {
  return (
    <section className="surface-panel border p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="section-title text-sm font-semibold uppercase tracking-wide">{title}</h2>
        <span className={`text-xs font-semibold uppercase tracking-wide ${live ? 'money-negative' : 'muted-text'}`}>
          {live ? 'Live money' : 'Paper'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1.5 lg:grid-cols-3 2xl:grid-cols-6">
        <Metric label="Total" value={stats.total} />
        <Metric label="Settled" value={stats.settled} />
        <Metric label="Unsettled" value={stats.unsettled} />
        <Metric label="Win Rate" value={fmtPct(stats.winRate)} />
        <Metric label="P/L" value={`$${stats.profitLoss}`} tone={moneyClass(stats.profitLoss)} />
        <Metric label="ROI" value={fmtPct(stats.roi)} />
      </div>
      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
        <SideCard label="YES" stats={stats.yes} icon={<TrendingUp size={16} />} />
        <SideCard label="NO" stats={stats.no} icon={<TrendingDown size={16} />} />
      </div>
    </section>
  );
}

function BucketTable({ title, buckets }: { title: string; buckets: BucketStats }) {
  const entries = Object.entries(buckets ?? {});

  return (
    <section className="surface-card border p-4">
      <h2 className="section-title mb-3 text-sm font-semibold uppercase tracking-wide">{title}</h2>
      <table className="w-full text-left text-sm">
        <thead className="muted-text text-xs">
          <tr><th className="pb-2">Bucket</th><th className="pb-2">Trades</th><th className="pb-2">Win</th><th className="pb-2">P/L</th></tr>
        </thead>
        <tbody>
          {entries.map(([name, item]) => (
            <tr className="row-border border-t" key={name}>
              <td className="py-2">{name}</td>
              <td>{item.total}</td>
              <td>{fmtPct(item.winRate)}</td>
              <td className={moneyClass(item.profitLoss)}>${item.profitLoss}</td>
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

function RecentTrades({ title, rows }: { title: string; rows: TradeRow[] }) {
  const items = rows ?? [];

  return (
    <section className="surface-card border p-4">
      <h2 className="section-title mb-3 text-sm font-semibold uppercase tracking-wide">{title}</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="muted-text text-xs">
            <tr><th>ID</th><th>Made</th><th>Ticker</th><th>Side</th><th>Entry</th><th>Result</th><th>P/L</th><th>Strategy</th></tr>
          </thead>
          <tbody>
            {items.map((row, index) => (
              <tr className="row-border border-t" key={`${row.ticker}-${index}`}>
                <td className="muted-text py-2 font-mono text-xs">{shortId(row.trade_id)}</td>
                <td className="py-2 whitespace-nowrap">{fmtDateTime(row.timestamp)}</td>
                <td className="max-w-[220px] truncate">{row.ticker}</td>
                <td>{row.side}</td>
                <td>{row.entry_price}</td>
                <td>{row.actual_result}</td>
                <td className={moneyClass(row.profit_loss)}>{row.profit_loss}</td>
                <td>{row.strategy_name}</td>
              </tr>
            ))}
            {!items.length && (
              <tr className="row-border border-t">
                <td className="muted-text py-3" colSpan={8}>No trades yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ShadowPanel({ shadow }: { shadow: ShadowStats }) {
  const blockedReasons = Object.entries(shadow.blockedReasons ?? {});

  return (
    <section className="surface-card border p-4">
      <div className="mb-3 flex items-center gap-2">
        <AlertTriangle size={16} className="text-amber-400" />
        <h2 className="section-title text-sm font-semibold uppercase tracking-wide">Blocked Signals</h2>
      </div>
      <Metric label="Shadow Signals" value={shadow.total} />
      <div className="mt-3 grid gap-2">
        {blockedReasons.map(([reason, count]) => (
          <div className="surface-soft flex items-center justify-between rounded border px-3 py-2 text-sm" key={reason}>
            <span>{reason}</span>
            <span className="font-semibold tabular-nums">{count}</span>
          </div>
        ))}
        {!blockedReasons.length && (
          <div className="surface-soft muted-text rounded border px-3 py-2 text-sm">No blocked signals yet</div>
        )}
      </div>
    </section>
  );
}

function BotControls({ bots, onAction }: { bots?: BotStatus[]; onAction: (botId: string, action: 'start' | 'stop') => void }) {
  const items = bots ?? [];

  return (
    <section className="surface-card rounded-lg border p-4">
      <div className="mb-3 flex items-center gap-2">
        <Bot size={16} className="muted-heading" />
        <h2 className="section-title text-sm font-semibold uppercase tracking-wide">Bot Control</h2>
      </div>
      <div className="grid gap-3 xl:grid-cols-3">
        {items.map((bot) => (
          <div className="surface-panel rounded-md border p-3" key={bot.id}>
            <div className="mb-2 flex items-start justify-between gap-2">
              <div>
                <div className="font-semibold">{bot.name}</div>
                <div className="muted-text mt-1 text-xs">{bot.mode === 'live' ? 'Real money' : 'Paper only'}</div>
              </div>
              <span className={`rounded px-2 py-1 text-xs font-medium ${bot.running ? 'status-running' : 'status-stopped'}`}>
                {bot.running ? `Running ${bot.pid ?? ''}` : 'Stopped'}
              </span>
            </div>
            <p className="muted-heading min-h-16 text-sm leading-5">{bot.description}</p>
            <div className="mt-3 flex items-center justify-between gap-2">
              <div className="muted-text truncate text-xs">{bot.logFile}</div>
              {bot.running ? (
                <button
                  onClick={() => onAction(bot.id, 'stop')}
                  className="danger-button inline-flex items-center gap-1 rounded-md border px-3 py-2 text-sm font-medium"
                >
                  <Square size={14} /> Stop
                </button>
              ) : (
                <button
                  onClick={() => onAction(bot.id, 'start')}
                  className={`inline-flex items-center gap-1 rounded-md px-3 py-2 text-sm font-medium ${
                    bot.mode === 'live'
                      ? 'bg-red-700 text-white hover:bg-red-800'
                      : 'primary-button text-white'
                  }`}
                >
                  <Play size={14} /> Start
                </button>
              )}
            </div>
          </div>
        ))}
        {!items.length && (
          <div className="surface-panel muted-heading rounded-md border p-3 text-sm">
            Bot controls unavailable. Restart the dashboard server so it serves the latest API.
          </div>
        )}
      </div>
    </section>
  );
}

function SingleBotControl({ bot, onAction }: { bot?: BotStatus; onAction: (botId: string, action: 'start' | 'stop') => void }) {
  if (!bot) {
    return (
      <section className="surface-card border p-4">
        <div className="muted-heading text-sm">Restart the dashboard server so this bot appears in the API.</div>
      </section>
    );
  }

  return (
    <section className="surface-card border p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Bot size={17} className="muted-heading" />
            <h2 className="text-lg font-semibold">{bot.name}</h2>
          </div>
          <div className="muted-text mt-1 text-sm">{bot.mode === 'live' ? 'Real money' : 'Paper only'}</div>
        </div>
        <span className={`status-text text-xs font-semibold uppercase tracking-wide ${bot.running ? 'money-positive' : 'muted-text'}`}>
          {bot.running ? `Running ${bot.pid ?? ''}` : 'Stopped'}
        </span>
      </div>
      <p className="muted-heading text-sm leading-6">{bot.description}</p>
      <div className="surface-soft mt-4 border px-3 py-2 text-xs">
        <div className="muted-text">Log file</div>
        <div className="mt-1 truncate font-medium">{bot.logFile}</div>
      </div>
      <div className="mt-4 flex justify-end">
        {bot.running ? (
          <button
            onClick={() => onAction(bot.id, 'stop')}
            className="danger-button inline-flex items-center justify-center gap-2 border px-3 py-2 text-sm font-medium"
          >
            <Square size={15} /> Stop
          </button>
        ) : (
          <button
            onClick={() => onAction(bot.id, 'start')}
            className={`inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium ${
              bot.mode === 'live'
                ? 'bg-red-700 text-white hover:bg-red-800'
                : 'primary-button text-white'
            }`}
          >
            <Play size={15} /> Start
          </button>
        )}
      </div>
    </section>
  );
}

function BotTabs({ active, onChange, data }: { active: TabId; onChange: (tab: TabId) => void; data: DashboardStats }) {
  const botById = Object.fromEntries((data.bots ?? []).map((bot) => [bot.id, bot]));
  const tabs: Array<{ id: TabId; label: string; detail: string; running?: boolean }> = [
    { id: 'btc15_paper', label: '15m Paper', detail: `${data.paper.total} trades`, running: botById.btc15_paper?.running },
    { id: 'btc15_live', label: '15m Live', detail: `${data.live.total} trades`, running: botById.btc15_live?.running },
    { id: 'scalp_paper', label: 'Scalp Paper', detail: `${data.scalp.total} entries`, running: botById.scalp_paper?.running },
    { id: 'shadow', label: 'Blocked Signals', detail: `${data.shadow.total} logged` },
  ];

  return (
    <aside className="surface-sidebar border-r">
      <div className="px-4 py-4">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wide muted-text">Bots</div>
        <div className="grid gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`tab-button px-3 py-3 text-left ${active === tab.id ? 'tab-button-active' : ''}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{tab.label}</span>
              {tab.running !== undefined && (
                <span className={`h-2.5 w-2.5 rounded-full ${tab.running ? 'bg-emerald-400' : 'bg-slate-500'}`} />
              )}
            </div>
            <div className="muted-text mt-1 text-xs">{tab.detail}</div>
          </button>
        ))}
        </div>
      </div>
    </aside>
  );
}

function SectionLabel({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="muted-text mt-1 text-sm">{subtitle}</p>
    </div>
  );
}

function RiskNotes() {
  return (
    <section className="surface-card border p-4">
      <div className="section-title mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide">
        <CircleDollarSign size={16} /> Risk Notes
      </div>
      <div className="grid gap-2 text-sm">
        <div className="surface-soft border px-3 py-2">Live mode max: 1 contract per trade</div>
        <div className="surface-soft border px-3 py-2">Daily live trade cap: 30</div>
        <div className="surface-soft border px-3 py-2">Daily loss stop: <code>KALSHI_MAX_DAILY_LIVE_LOSS</code></div>
      </div>
    </section>
  );
}

function CountTable({ title, rows }: { title: string; rows: Record<string, number> }) {
  const entries = Object.entries(rows ?? {});

  return (
    <section className="surface-card border p-4">
      <h2 className="section-title mb-3 text-sm font-semibold uppercase tracking-wide">{title}</h2>
      <div className="grid gap-1.5">
        {entries.map(([name, count]) => (
          <div className="surface-soft flex items-center justify-between border px-3 py-2 text-sm" key={name}>
            <span>{name}</span>
            <span className="font-semibold tabular-nums">{count}</span>
          </div>
        ))}
        {!entries.length && (
          <div className="surface-soft muted-text border px-3 py-2 text-sm">No data yet</div>
        )}
      </div>
    </section>
  );
}

function ScalpPanel({ stats }: { stats: ScalpStats }) {
  return (
    <section className="surface-panel border">
      <div className="table-header flex items-center justify-between border-b px-3 py-2">
        <h2 className="section-title text-xs font-semibold uppercase tracking-wide">Scalp Paper</h2>
        <span className="muted-text text-xs font-semibold uppercase tracking-wide">5s momentum</span>
      </div>
      <div className="grid grid-cols-2 gap-1.5 p-3 lg:grid-cols-3 2xl:grid-cols-6">
        <Metric label="Entries" value={stats.total} />
        <Metric label="Closed" value={stats.closed} />
        <Metric label="Open" value={stats.open} />
        <Metric label="Win Rate" value={fmtPct(stats.winRate)} />
        <Metric label="P/L" value={`$${stats.profitLoss}`} tone={moneyClass(stats.profitLoss)} />
        <Metric label="Peak P/L" value={`$${stats.peakProfit}`} tone={moneyClass(stats.peakProfit)} />
      </div>
    </section>
  );
}

function ScalpTrades({ rows }: { rows: TradeRow[] }) {
  const items = rows ?? [];

  return (
    <section className="surface-card border">
      <div className="table-header flex items-center justify-between border-b px-3 py-2">
        <h2 className="section-title text-xs font-semibold uppercase tracking-wide">Recent Scalp Events</h2>
        <span className="muted-text text-xs tabular-nums">{items.length} rows</span>
      </div>
      <div className="max-h-[520px] overflow-auto">
        <table className="compact-table w-full text-left">
          <thead className="muted-text text-xs">
            <tr><th>ID</th><th>Event</th><th>Side</th><th>Opened</th><th>Sold</th><th>Entry</th><th>Exit</th><th>P/L</th><th>Reason</th></tr>
          </thead>
          <tbody>
            {items.map((row, index) => (
              <tr className={`row-border border-t ${eventRowClass(row.event)}`} key={`${row.trade_id}-${row.event}-${index}`}>
                <td className="muted-text py-2 font-mono text-xs">{shortId(row.trade_id)}</td>
                <td className={`font-semibold ${eventClass(row.event)}`}>{row.event}</td>
                <td>{row.side}</td>
                <td className="py-2 whitespace-nowrap">{fmtDateTime(row.opened_at || (row.event === 'OPEN' ? row.timestamp : ''))}</td>
                <td className="py-2 whitespace-nowrap">{fmtDateTime(row.closed_at || (row.event === 'CLOSE' ? row.timestamp : ''))}</td>
                <td>{row.entry_price}</td>
                <td>{row.exit_price}</td>
                <td className={moneyClass(row.profit_loss)}>{row.profit_loss}</td>
                <td className="max-w-[320px] truncate" title={row.reason}>{row.reason}</td>
              </tr>
            ))}
            {!items.length && (
              <tr className="row-border border-t">
                <td className="muted-text py-3" colSpan={9}>No scalp events yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ShadowTrades({ rows }: { rows: TradeRow[] }) {
  const items = rows ?? [];

  return (
    <section className="surface-card border p-4">
      <h2 className="section-title mb-3 text-sm font-semibold uppercase tracking-wide">Recent Blocked Signals</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="muted-text text-xs">
            <tr><th>Time</th><th>Ticker</th><th>Decision</th><th>Side</th><th>Price</th><th>Reason</th></tr>
          </thead>
          <tbody>
            {items.map((row, index) => (
              <tr className="row-border border-t" key={`${row.ticker}-${row.reason}-${index}`}>
                <td className="py-2 whitespace-nowrap">{fmtDateTime(row.timestamp)}</td>
                <td className="max-w-[220px] truncate">{row.ticker}</td>
                <td>{row.decision}</td>
                <td>{row.side}</td>
                <td>{row.entry_price ?? row.price}</td>
                <td className="max-w-[360px] truncate">{row.reason}</td>
              </tr>
            ))}
            {!items.length && (
              <tr className="row-border border-t">
                <td className="muted-text py-3" colSpan={6}>No blocked signals yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BotWorkspace({ active, data, onAction }: { active: TabId; data: DashboardStats; onAction: (botId: string, action: 'start' | 'stop') => void }) {
  const botById = Object.fromEntries((data.bots ?? []).map((bot) => [bot.id, bot]));

  if (active === 'btc15_paper') {
    return (
      <div className="grid gap-3 2xl:grid-cols-[300px_1fr]">
        <div className="grid content-start gap-3">
          <SingleBotControl bot={botById.btc15_paper} onAction={onAction} />
          <BucketTable title="Paper by Strategy" buckets={data.paper.byStrategy} />
          <BucketTable title="Paper by Time" buckets={data.paper.byTime} />
        </div>
        <div className="grid content-start gap-3">
          <TradePanel title="15m Paper Trading" stats={data.paper} />
          <RecentTrades title="Recent Paper Trades" rows={data.paper.recent} />
        </div>
      </div>
    );
  }

  if (active === 'btc15_live') {
    return (
      <div className="grid gap-3 2xl:grid-cols-[300px_1fr]">
        <div className="grid content-start gap-3">
          <SingleBotControl bot={botById.btc15_live} onAction={onAction} />
          <RiskNotes />
          <BucketTable title="Live by Strategy" buckets={data.live.byStrategy} />
          <BucketTable title="Live by Time" buckets={data.live.byTime} />
        </div>
        <div className="grid content-start gap-3">
          <TradePanel title="15m Live Trading" stats={data.live} live />
          <RecentTrades title="Recent Live Trades" rows={data.live.recent} />
        </div>
      </div>
    );
  }

  if (active === 'scalp_paper') {
    return (
      <div className="grid gap-3 2xl:grid-cols-[280px_1fr]">
        <div className="grid content-start gap-3">
          <SingleBotControl bot={botById.scalp_paper} onAction={onAction} />
          <CountTable title="Scalp Reasons" rows={data.scalp.byReason} />
        </div>
        <div className="grid content-start gap-3">
          <ScalpPanel stats={data.scalp} />
          <ScalpTrades rows={data.scalp.recent} />
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-3 2xl:grid-cols-[300px_1fr]">
      <div className="grid content-start gap-3">
        <ShadowPanel shadow={data.shadow} />
        <CountTable title="Shadow Decisions" rows={data.shadow.decisions} />
      </div>
      <ShadowTrades rows={data.shadow.recent} />
    </div>
  );
}

function App() {
  const [data, setData] = React.useState<DashboardStats | null>(null);
  const [updated, setUpdated] = React.useState('');
  const [theme, setTheme] = React.useState(() => localStorage.getItem('dashboard-theme') ?? 'dark');
  const [activeTab, setActiveTab] = React.useState<TabId>('btc15_paper');

  const load = React.useCallback(async () => {
    const response = await fetch('/api/stats');
    const payload = await response.json() as DashboardStats;
    setData({
      ...payload,
      bots: payload.bots ?? [],
      scalp: payload.scalp ?? emptyScalp,
    });
    setUpdated(new Date().toLocaleTimeString());
  }, []);

  const botAction = React.useCallback(async (botId: string, action: 'start' | 'stop') => {
    await fetch(`/api/bots/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ botId }),
    });
    await load();
  }, [load]);

  React.useEffect(() => {
    void load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  React.useEffect(() => {
    localStorage.setItem('dashboard-theme', theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  if (!data) {
    return <div className="p-6 text-slate-600">Loading dashboard...</div>;
  }

  return (
    <div className="app-shell min-h-screen">
      <header className="surface-header border-b px-4 py-3">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-5">
            <div className="flex items-center gap-2">
              <Gauge size={18} className="text-emerald-400" />
              <h1 className="text-lg font-semibold tracking-tight">Kalshi BTC</h1>
            </div>
            <nav className="hidden items-center gap-5 text-xs font-semibold uppercase tracking-[0.22em] md:flex">
              <span className="terminal-nav-active">Bots</span>
              <span className="muted-text">Trades</span>
              <span className="muted-text">Risk</span>
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="surface-button inline-flex items-center gap-2 border px-3 py-2 text-sm font-medium"
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
            <button onClick={load} className="surface-button inline-flex items-center gap-2 border px-3 py-2 text-sm font-medium">
              <RefreshCw size={16} /> {updated || 'Refresh'}
            </button>
            <button className="surface-button inline-flex items-center gap-2 border px-3 py-2 text-sm font-medium md:hidden">
              <Menu size={16} />
            </button>
          </div>
        </div>
      </header>
      <main className="dashboard-frame mx-auto max-w-[1180px]">
        <BotTabs active={activeTab} onChange={setActiveTab} data={data} />
        <section className="dashboard-content">
          <BotWorkspace active={activeTab} data={data} onAction={botAction} />
          <div className="muted-text flex items-center gap-2 pb-4 pt-2 text-xs">
            <Activity size={14} /> Auto-refreshes every 5 seconds.
          </div>
        </section>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
