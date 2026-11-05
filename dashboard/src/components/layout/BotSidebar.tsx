import type { DashboardStats } from '../../types/dashboard';
import type { TabId } from '../../types/bots';
import { BOT_NAMES, BOT_NAV_GROUPS } from '../../content/bots';

function tradeCount(total: number): string {
  return `${total} ${total === 1 ? 'trade' : 'trades'}`;
}

export function BotSidebar({ active, onChange, data }: { active: TabId; onChange: (tab: TabId) => void; data: DashboardStats }) {
  const botById = Object.fromEntries((data.bots ?? []).map((bot) => [bot.id, bot]));
  const details: Record<TabId, string> = {
    btc15_paper: tradeCount(data.paper.total),
    btc15_dual_paper: tradeCount(data.dualPaper.total),
    btc15_direction_paper: tradeCount(data.directionPaper.total),
    scalp_paper: `${data.scalp.total} ${data.scalp.total === 1 ? 'entry' : 'entries'}`,
    btc15_live: tradeCount(data.live.total),
    btc15_dual_live: tradeCount(data.dualLive.total),
    shadow: `${data.shadow.total} logged`,
  };

  return (
    <aside className="surface-sidebar border-r">
      <nav className="bot-navigation" aria-label="Bot workspaces">
        {BOT_NAV_GROUPS.map((group) => (
          <section key={group.id} className="bot-nav-group" aria-labelledby={`bot-group-${group.id}`}>
            <h2 id={`bot-group-${group.id}`} className="bot-nav-heading">{group.label}</h2>
            <div className="bot-nav-grid">
              {group.tabs.map((id) => {
                const bot = botById[id];
                const running = bot && (bot.running || !!bot.runtime?.processAlive);
                return (
                  <button
                    key={id}
                    onClick={() => onChange(id)}
                    aria-current={active === id ? 'true' : undefined}
                    className={`tab-button ${active === id ? 'tab-button-active' : ''}`}
                  >
                    <span className="bot-nav-title">
                      <span>{id === 'shadow' ? 'Blocked Signals' : BOT_NAMES[id]}</span>
                      {bot && (
                        <span aria-label={running ? 'Running' : 'Stopped'} className={`bot-nav-status ${running ? 'status-dot-running' : 'status-dot-stopped'}`} />
                      )}
                    </span>
                    <span className="bot-nav-detail">{details[id]}</span>
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </nav>
    </aside>
  );
}
