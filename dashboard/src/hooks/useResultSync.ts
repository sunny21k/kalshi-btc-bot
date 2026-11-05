import React from 'react';
import { cancelResultSync, fetchResultSync, startResultSync } from '../api/dashboard';
import type { ResultSync } from '../types/dashboard';

export function useResultSync(sync: ResultSync | undefined, onSync: (sync?: ResultSync) => void, load: () => Promise<void>) {
  const [syncRequestPending, setSyncRequestPending] = React.useState(false);
  const [stopRequestPending, setStopRequestPending] = React.useState(false);
  const [refreshError, setRefreshError] = React.useState('');

  const updateResults = React.useCallback(async () => {
    if (syncRequestPending || sync?.running) return;
    setSyncRequestPending(true);
    setRefreshError('');
    try {
      const result = await startResultSync();
      onSync(result.resultSync);
      await load();
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : 'Could not update results');
    } finally {
      setSyncRequestPending(false);
    }
  }, [sync?.running, syncRequestPending, onSync, load]);

  const stopResultsRefresh = React.useCallback(async () => {
    if (stopRequestPending || !sync?.running || sync.stopping) return;
    setStopRequestPending(true);
    setRefreshError('');
    try {
      const result = await cancelResultSync();
      onSync(result.resultSync);
      await load();
    } catch (error) {
      setRefreshError(error instanceof Error ? error.message : 'Could not stop results refresh');
    } finally {
      setStopRequestPending(false);
    }
  }, [sync?.running, sync?.stopping, stopRequestPending, onSync, load]);

  React.useEffect(() => {
    if (!sync?.running) return;
    let active = true;
    let polling = false;
    const timer = window.setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const status = await fetchResultSync();
        if (!active) return;
        onSync(status);
        setRefreshError('');
        if (!status.running) await load();
      } catch (error) {
        if (active) setRefreshError(error instanceof Error ? error.message : 'Could not check results update');
      } finally {
        polling = false;
      }
    }, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [sync?.running, onSync, load]);

  return { syncRequestPending, stopRequestPending, refreshError, updateResults, stopResultsRefresh };
}
