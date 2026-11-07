import type { BotAction, TabId } from '../../types/bots';
import type { DashboardStats } from '../../types/dashboard';
import { BOT_NAMES } from '../../content/bots';
import { BotControl } from './BotControl';
import { BotDiagnostics } from './BotDiagnostics';
import { RiskNotes } from './RiskNotes';
import { BotPerformance } from '../performance/BotPerformance';
import { BucketTable } from '../stats/BucketTable';
import { CountTable } from '../stats/CountTable';
import { ScalpPanel } from '../stats/ScalpPanel';
import { ShadowPanel } from '../stats/ShadowPanel';
import { TradePanel } from '../stats/TradePanel';
import { RecentTrades } from '../trades/RecentTrades';
import { ScalpTrades } from '../trades/ScalpTrades';
import { ShadowTrades } from '../trades/ShadowTrades';

export function BotWorkspace({ active, data, onAction, onSettingsSaved }: { active: TabId; data: DashboardStats; onAction: BotAction; onSettingsSaved?: () => Promise<void> }) {
  const botById = Object.fromEntries((data.bots ?? []).map((bot) => [bot.id, bot]));

  if (active === 'btc15_paper' || active === 'btc15_dual_paper' || active === 'btc15_direction_paper') {
    const stats = active === 'btc15_direction_paper' ? data.directionPaper : active === 'btc15_dual_paper' ? data.dualPaper : data.paper;
    const title = `${BOT_NAMES[active]} paper trading`;
    return (
      <div className="bot-workspace grid gap-3">
        <BotPerformance key={active} data={stats.performance} />
        <div className="bot-overview">
          <BotControl key={active} bot={botById[active]} onAction={onAction} onSettingsSaved={onSettingsSaved} />
          <BotDiagnostics runtime={botById[active]?.runtime} />
          <TradePanel title={title} stats={stats} />
        </div>
        <RecentTrades title="Recent Paper Trades" rows={stats.recent} botId={active} />
        <BucketTable title="Paper by Strategy" buckets={stats.byStrategy} />
      </div>
    );
  }

  if (active === 'btc15_live' || active === 'btc15_dual_live') {
    const stats = active === 'btc15_dual_live' ? data.dualLive : data.live;
    return (
      <div className="bot-workspace grid gap-3">
        <BotPerformance key={active} data={stats.performance} />
        <div className="bot-overview">
          <BotControl key={active} bot={botById[active]} onAction={onAction} onSettingsSaved={onSettingsSaved} />
          <BotDiagnostics runtime={botById[active]?.runtime} />
          <TradePanel title={`${BOT_NAMES[active]} live trading`} stats={stats} live />
        </div>
        <RecentTrades title="Recent Live Orders" rows={stats.recent} live botId={active} />
        <BucketTable title="Live by Strategy" buckets={stats.byStrategy} />
        <RiskNotes dailyLimit={botById[active]?.dailyLiveOrderLimit} />
      </div>
    );
  }

  if (active === 'scalp_paper') {
    return (
      <div className="bot-workspace grid gap-3">
        <BotPerformance key={active} data={data.scalp.performance} />
        <div className="bot-overview">
          <BotControl bot={botById.scalp_paper} onAction={onAction} onSettingsSaved={onSettingsSaved} />
          <BotDiagnostics runtime={botById.scalp_paper?.runtime} />
          <ScalpPanel stats={data.scalp} />
        </div>
        <ScalpTrades rows={data.scalp.recent} />
        <CountTable title="Scalp Reasons" rows={data.scalp.byReason} />
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
