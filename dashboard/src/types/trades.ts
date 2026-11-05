import type { PerformanceData } from './performance';

export type SideStats = {
  total: number;
  settled: number;
  winRate: number | null;
  profitLoss: string;
};

export type TradeRow = Record<string, string>;

export type BucketStats = Record<string, SideStats>;

export type TradeStats = {
  performance?: PerformanceData;
  total: number;
  settled: number;
  unsettled: number;
  wins: number;
  losses: number;
  winRate: number | null;
  totalInvested: string;
  totalTraded: string;
  profitLoss: string;
  roi: number | null;
  yes: SideStats;
  no: SideStats;
  byStrategy: BucketStats;
  byTime: BucketStats;
  recent: TradeRow[];
};

export type ShadowStats = {
  total: number;
  decisions: Record<string, number>;
  blockedReasons: Record<string, number>;
  recent: TradeRow[];
};

export type ScalpStats = {
  performance?: PerformanceData;
  total: number;
  closed: number;
  open: number;
  wins: number;
  losses: number;
  winRate: number | null;
  totalInvested: string;
  profitLoss: string;
  peakProfit: string;
  byReason: Record<string, number>;
  recent: TradeRow[];
};
