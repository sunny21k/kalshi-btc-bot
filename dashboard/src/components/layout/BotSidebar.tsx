import type { DashboardStats } from '../../types/dashboard';
import type { TabId } from '../../types/bots';

export function BotSidebar({ active, onChange, data }: { active: TabId; onChange: (tab: TabId) => void; data: DashboardStats }) {
  const botById = Object.fromEntries((data.bots ?? []).map((bot) => [bot.id, bot]));
  const tabs: Array<{ id: TabId; label: string; detail: string; running?: boolean }> = [
    { id: 'btc15_paper', label: '15m NO Only', detail: `${data.paper.total} trades`, running: botById.btc15_paper?.running },
    { id: 'btc15_dual_paper', label: '15m YES / NO', detail: `${data.dualPaper.total} trades`, running: botById.btc15_dual_paper?.running },
    { id: 'btc15_direction_paper', label: '15m Direction', detail: `${data.directionPaper.total} trades`, running: botById.btc15_direction_paper?.running },
    { id: 'btc15_live', label: '15m Live', detail: `${data.live.total} trades`, running: botById.btc15_live?.running },
    { id: 'btc15_dual_live', label: 'YES / NO Live', detail: `${data.dualLive.total} trades`, running: botById.btc15_dual_live?.running },
    { id: 'scalp_paper', label: 'Scalp Paper', detail: `${data.scalp.total} entries`, running: botById.scalp_paper?.running },
    { id: 'shadow', label: 'Blocked Signals', detail: `${data.shadow.total} logged` },
  ];

  return (
    <aside className="surface-sidebar border-r">
      <div className="px-4 py-4">
        <div className="mb-3 text-xs font-semibold uppercase tracking-wide muted-text">Bots</div>
        <div className="bot-nav-grid grid gap-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`tab-button px-3 py-3 text-left ${active === tab.id ? 'tab-button-active' : ''}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold">{tab.label}</span>
              {tab.running !== undefined && (
                <span className={`h-2.5 w-2.5 rounded-full ${tab.running ? 'status-dot-running' : 'status-dot-stopped'}`} />
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
