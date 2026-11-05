import React from 'react';
import { fetchDashboardStats } from '../api/dashboard';
import { normalizeDashboard } from '../lib/dashboard';
import type { DashboardStats, ResultSync } from '../types/dashboard';

export function useDashboardData() {
  const [data, setData] = React.useState<DashboardStats | null>(null);
  const [updated, setUpdated] = React.useState('');

  const load = React.useCallback(async () => {
    const payload = await fetchDashboardStats();
    setData(normalizeDashboard(payload));
    setUpdated(new Date().toLocaleTimeString());
  }, []);

  const setResultSync = React.useCallback((sync?: ResultSync) => {
    setData((current) => current ? { ...current, resultSync: sync } : current);
  }, []);

  React.useEffect(() => {
    void load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  return { data, updated, load, setResultSync };
}
