import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { BotWorkspace } from './components/bots/BotWorkspace';
import { InfoPage } from './components/info/InfoPage';
import { BotSidebar } from './components/layout/BotSidebar';
import { DashboardFooter } from './components/layout/DashboardFooter';
import { DashboardHeader } from './components/layout/DashboardHeader';
import { AppLink } from './components/layout/AppLink';
import { ResultSyncStatus } from './components/results/ResultSyncStatus';
import { useBotActions } from './hooks/useBotActions';
import { useDashboardData } from './hooks/useDashboardData';
import { useResultSync } from './hooks/useResultSync';
import { useTheme } from './hooks/useTheme';
import { useAppNavigation } from './hooks/useAppNavigation';
import type { TabId } from './types/bots';

export function App() {
  const { data, updated, load, setResultSync, loadError } = useDashboardData();
  const { theme, toggleTheme } = useTheme();
  const location = useAppNavigation();
  const [activeTab, setActiveTab] = React.useState<TabId>('btc15_paper');
  const { botAction, actionError } = useBotActions(data?.bots ?? [], load);
  const { syncRequestPending, stopRequestPending, refreshError, updateResults, stopResultsRefresh } =
    useResultSync(data?.resultSync, setResultSync, load);

  return (
    <div className="app-shell min-h-screen">
      <DashboardHeader
        theme={theme}
        onToggleTheme={toggleTheme}
        sync={data?.resultSync}
        activePage={location.page}
        dashboardReady={!!data}
        syncRequestPending={syncRequestPending}
        stopRequestPending={stopRequestPending}
        onUpdateResults={updateResults}
        onStopRefresh={stopResultsRefresh}
      />
      {location.page === 'info' && (
        <main className="info-frame mx-auto max-w-[1180px]">
          <InfoPage section={location.section} />
          <DashboardFooter updated={updated} showUpdates={false} />
        </main>
      )}
      {location.page === 'bots' && data && (
        <main id="bots" className="dashboard-frame mx-auto max-w-[1180px]">
          <BotSidebar active={activeTab} onChange={setActiveTab} data={data} />
          <section className="dashboard-content">
            {loadError && <p className="money-negative text-xs" role="status">Connection update: {loadError}. Retrying automatically.</p>}
            {actionError && (
              <div role="alert" className="money-negative flex items-center gap-2 text-sm">
                <AlertTriangle size={16} className="shrink-0" /> {actionError}
              </div>
            )}
            <ResultSyncStatus sync={data.resultSync} pending={syncRequestPending} error={refreshError} />
            <BotWorkspace active={activeTab} data={data} onAction={botAction} />
            <DashboardFooter updated={updated} />
          </section>
        </main>
      )}
      {location.page === 'bots' && !data && (
        <main id="bots" className="dashboard-loading mx-auto max-w-[1180px]">
          <h2>{loadError ? 'Waiting for the bot server' : 'Connecting to the dashboard'}</h2>
          <p>{loadError || 'Loading bot activity and trade results...'}</p>
          <p>Info & FAQ is available while the dashboard connects.</p>
          <AppLink className="info-text-link" href="/info">Open Info & FAQ</AppLink>
        </main>
      )}
    </div>
  );
}
