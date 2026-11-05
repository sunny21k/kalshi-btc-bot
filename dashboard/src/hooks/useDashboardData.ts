import React from 'react';
import { fetchDashboardStats } from '../api/dashboard';
import { normalizeDashboard } from '../lib/dashboard';
import type { DashboardStats, ResultSync } from '../types/dashboard';

export function useDashboardData() {
  const [data, setData] = React.useState<DashboardStats | null>(null);
  const [updated, setUpdated] = React.useState('');
  const [loadError, setLoadError] = React.useState('');

  const load = React.useCallback(async () => {
    try {
      const payload = await fetchDashboardStats();
      setData(normalizeDashboard(payload));
      setUpdated(new Date().toLocaleTimeString());
      setLoadError('');
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Could not connect to the dashboard');
      throw error;
    }
  }, []);

  const setResultSync = React.useCallback((sync?: ResultSync) => {
    setData((current) => current ? { ...current, resultSync: sync } : current);
  }, []);

  React.useEffect(() => {
    const poll = () => { void load().catch(() => {}); };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  return { data, updated, load, setResultSync, loadError };
}
