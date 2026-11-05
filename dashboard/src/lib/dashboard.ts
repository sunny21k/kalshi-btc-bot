import type { DashboardStats } from '../types/dashboard';
import type { ScalpStats, TradeStats } from '../types/trades';

export const emptyTrade: TradeStats = {
  total: 0,
  settled: 0,
  unsettled: 0,
  wins: 0,
  losses: 0,
  winRate: null,
  totalInvested: '0.0000',
  totalTraded: '0.0000',
  profitLoss: '0.0000',
  roi: null,
  yes: { total: 0, settled: 0, winRate: null, profitLoss: '0.0000' },
  no: { total: 0, settled: 0, winRate: null, profitLoss: '0.0000' },
  byStrategy: {},
  byTime: {},
  recent: [],
};

export const emptyScalp: ScalpStats = {
  total: 0,
  closed: 0,
  open: 0,
  wins: 0,
  losses: 0,
  winRate: null,
  totalInvested: '0.0000',
  profitLoss: '0.0000',
  peakProfit: '0.0000',
  byReason: {},
  recent: [],
};

export function normalizeDashboard(payload: DashboardStats): DashboardStats {
  return {
    ...payload,
    bots: payload.bots ?? [],
    dualPaper: payload.dualPaper ?? emptyTrade,
    dualLive: payload.dualLive ?? emptyTrade,
    scalp: payload.scalp ?? emptyScalp,
  };
}
