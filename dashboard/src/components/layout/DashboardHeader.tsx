import { Gauge, Moon, RefreshCw, Square, Sun } from 'lucide-react';
import type { ResultSync } from '../../types/dashboard';
import type { AppPage } from '../../types/navigation';
import { AppLink } from './AppLink';

type Props = {
  theme: string;
  onToggleTheme: () => void;
  sync?: ResultSync;
  syncRequestPending: boolean;
  stopRequestPending: boolean;
  onUpdateResults: () => void;
  onStopRefresh: () => void;
  activePage?: AppPage;
  dashboardReady?: boolean;
};

export function DashboardHeader({ theme, onToggleTheme, sync, syncRequestPending, stopRequestPending, onUpdateResults, onStopRefresh, activePage = 'bots', dashboardReady = true }: Props) {
  return (
    <header className="surface-header border-b px-4 py-3">
      <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3">
        <div className="app-header-navigation">
          <div className="app-brand flex items-center gap-2">
            <Gauge size={18} className="accent-text" />
            <h1 className="text-lg font-semibold tracking-tight">Kalshi BTC</h1>
          </div>
          <nav className="app-navigation" aria-label="Main navigation">
            <AppLink href="/bots" aria-current={activePage === 'bots' ? 'page' : undefined}>Bots</AppLink>
            <AppLink href="/info" aria-current={activePage === 'info' ? 'page' : undefined}>Info & FAQ</AppLink>
          </nav>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={onToggleTheme}
            className="surface-button inline-flex items-center gap-2 border px-3 py-2 text-sm font-medium"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
          {(activePage === 'bots' || sync?.running) && <button
            onClick={onUpdateResults}
            disabled={!dashboardReady || syncRequestPending || sync?.running}
            title="Update fills, fees, settlements, and P/L"
            className="surface-button inline-flex min-w-[152px] items-center justify-center gap-2 border px-3 py-2 text-sm font-medium disabled:cursor-wait disabled:opacity-70"
          >
            <RefreshCw size={16} className={syncRequestPending || sync?.running ? 'animate-spin' : ''} />
            {syncRequestPending || sync?.running ? 'Updating...' : 'Update results'}
          </button>}
          {sync?.running && (
            <button
              onClick={onStopRefresh}
              disabled={stopRequestPending || sync.stopping}
              title="Stop only the results refresh; keep saved updates"
              className="surface-button inline-flex min-w-[128px] items-center justify-center gap-2 border px-3 py-2 text-sm font-medium disabled:cursor-wait disabled:opacity-70"
            >
              <Square size={15} />
              {stopRequestPending || sync.stopping ? 'Stopping...' : 'Stop refresh'}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
