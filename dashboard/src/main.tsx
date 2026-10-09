import React from 'react';
import ReactDOM from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  CircleDollarSign,
  RefreshCw,
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

type DashboardStats = {
  paper: TradeStats;
  live: TradeStats;
  shadow: ShadowStats;
};

const moneyClass = (value: string) => Number(value || 0) >= 0 ? 'text-emerald-700' : 'text-red-700';
const fmtPct = (value: number | null) => value === null ? 'N/A' : `${value.toFixed(2)}%`;

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${tone ?? 'text-slate-950'}`}>{value}</div>
    </div>
  );
}

function SideCard({ label, stats, icon }: { label: string; stats: SideStats; icon: React.ReactNode }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">{icon}{label}</div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <div><div className="text-xs text-slate-500">Trades</div><div className="font-semibold">{stats.total}</div></div>
        <div><div className="text-xs text-slate-500">Win Rate</div><div className="font-semibold">{fmtPct(stats.winRate)}</div></div>
        <div><div className="text-xs text-slate-500">P/L</div><div className={`font-semibold ${moneyClass(stats.profitLoss)}`}>${stats.profitLoss}</div></div>
      </div>
    </div>
  );
}

function TradePanel({ title, stats, live }: { title: string; stats: TradeStats; live?: boolean }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">{title}</h2>
        <span className={`rounded px-2 py-1 text-xs font-medium ${live ? 'bg-red-100 text-red-700' : 'bg-slate-200 text-slate-700'}`}>
          {live ? 'Live money' : 'Paper'}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
        <Metric label="Total" value={stats.total} />
        <Metric label="Settled" value={stats.settled} />
        <Metric label="Unsettled" value={stats.unsettled} />
        <Metric label="Win Rate" value={fmtPct(stats.winRate)} />
        <Metric label="P/L" value={`$${stats.profitLoss}`} tone={moneyClass(stats.profitLoss)} />
        <Metric label="ROI" value={fmtPct(stats.roi)} />
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <SideCard label="YES" stats={stats.yes} icon={<TrendingUp size={16} />} />
        <SideCard label="NO" stats={stats.no} icon={<TrendingDown size={16} />} />
      </div>
    </section>
  );
}

function BucketTable({ title, buckets }: { title: string; buckets: BucketStats }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-600">{title}</h2>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-slate-500">
          <tr><th className="pb-2">Bucket</th><th className="pb-2">Trades</th><th className="pb-2">Win</th><th className="pb-2">P/L</th></tr>
        </thead>
        <tbody>
          {Object.entries(buckets).map(([name, item]) => (
            <tr className="border-t border-slate-100" key={name}>
              <td className="py-2">{name}</td>
              <td>{item.total}</td>
              <td>{fmtPct(item.winRate)}</td>
              <td className={moneyClass(item.profitLoss)}>${item.profitLoss}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RecentTrades({ title, rows }: { title: string; rows: TradeRow[] }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-600">{title}</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-slate-500">
            <tr><th>Time</th><th>Ticker</th><th>Side</th><th>Entry</th><th>Result</th><th>P/L</th><th>Strategy</th></tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr className="border-t border-slate-100" key={`${row.ticker}-${index}`}>
                <td className="py-2">{(row.timestamp ?? '').slice(11, 19)}</td>
                <td className="max-w-[220px] truncate">{row.ticker}</td>
                <td>{row.side}</td>
                <td>{row.entry_price}</td>
                <td>{row.actual_result}</td>
                <td className={moneyClass(row.profit_loss)}>{row.profit_loss}</td>
                <td>{row.strategy_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ShadowPanel({ shadow }: { shadow: ShadowStats }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="mb-3 flex items-center gap-2">
        <AlertTriangle size={16} className="text-amber-600" />
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">Blocked Signals</h2>
      </div>
      <Metric label="Shadow Signals" value={shadow.total} />
      <div className="mt-3 grid gap-2">
        {Object.entries(shadow.blockedReasons).map(([reason, count]) => (
          <div className="flex items-center justify-between rounded border border-slate-100 px-3 py-2 text-sm" key={reason}>
            <span>{reason}</span>
            <span className="font-semibold tabular-nums">{count}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function App() {
  const [data, setData] = React.useState<DashboardStats | null>(null);
  const [updated, setUpdated] = React.useState('');

  const load = React.useCallback(async () => {
    const response = await fetch('/api/stats');
    const payload = await response.json() as DashboardStats;
    setData(payload);
    setUpdated(new Date().toLocaleTimeString());
  }, []);

  React.useEffect(() => {
    void load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  if (!data) {
    return <div className="p-6 text-slate-600">Loading dashboard...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <header className="border-b border-slate-200 bg-white px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">Kalshi BTC Bot</h1>
            <p className="text-sm text-slate-500">Live trade monitor and paper performance</p>
          </div>
          <button onClick={load} className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50">
            <RefreshCw size={16} /> {updated || 'Refresh'}
          </button>
        </div>
      </header>
      <main className="grid gap-4 p-4">
        <div className="grid gap-4 xl:grid-cols-2">
          <TradePanel title="Paper Trading" stats={data.paper} />
          <TradePanel title="Live Trading" stats={data.live} live />
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <BucketTable title="Paper by Strategy" buckets={data.paper.byStrategy} />
          <BucketTable title="Live by Strategy" buckets={data.live.byStrategy} />
          <ShadowPanel shadow={data.shadow} />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <RecentTrades title="Recent Paper Trades" rows={data.paper.recent} />
          <RecentTrades title="Recent Live Trades" rows={data.live.recent} />
        </div>
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-600">
            <CircleDollarSign size={16} /> Risk Notes
          </div>
          <div className="grid gap-2 text-sm text-slate-600 md:grid-cols-3">
            <div>Live mode max: 1 contract per trade</div>
            <div>Daily live trade cap: 30</div>
            <div>Daily loss stop: <code>KALSHI_MAX_DAILY_LIVE_LOSS</code></div>
          </div>
        </section>
        <div className="flex items-center gap-2 pb-4 text-xs text-slate-500">
          <Activity size={14} /> Auto-refreshes every 5 seconds.
        </div>
      </main>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(<App />);
