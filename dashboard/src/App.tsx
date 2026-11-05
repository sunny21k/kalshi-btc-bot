import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { BotWorkspace } from './components/bots/BotWorkspace';
import { BotSidebar } from './components/layout/BotSidebar';
import { DashboardFooter } from './components/layout/DashboardFooter';
import { DashboardHeader } from './components/layout/DashboardHeader';
import { ResultSyncStatus } from './components/results/ResultSyncStatus';
import { useBotActions } from './hooks/useBotActions';
import { useDashboardData } from './hooks/useDashboardData';
import { useResultSync } from './hooks/useResultSync';
import { useTheme } from './hooks/useTheme';
import type { TabId } from './types/bots';

export function App() {
  const { data, updated, load, setResultSync } = useDashboardData();
  const { theme, toggleTheme } = useTheme();
  const [activeTab, setActiveTab] = React.useState<TabId>('btc15_paper');
  const { botAction, actionError } = useBotActions(data?.bots ?? [], load);
  const { syncRequestPending, stopRequestPending, refreshError, updateResults, stopResultsRefresh } =
    useResultSync(data?.resultSync, setResultSync, load);

  if (!data) return <div className="muted-heading p-6">Loading dashboard...</div>;

  return (
    <div className="app-shell min-h-screen">
      <DashboardHeader
        theme={theme}
        onToggleTheme={toggleTheme}
        sync={data.resultSync}
        syncRequestPending={syncRequestPending}
        stopRequestPending={stopRequestPending}
        onUpdateResults={updateResults}
        onStopRefresh={stopResultsRefresh}
      />
      <main className="dashboard-frame mx-auto max-w-[1180px]">
        <BotSidebar active={activeTab} onChange={setActiveTab} data={data} />
        <section className="dashboard-content">
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
    </div>
  );
}
