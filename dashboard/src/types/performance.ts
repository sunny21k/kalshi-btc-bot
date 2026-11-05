export type PerformanceDay = {
  date: string;
  profitLoss: string;
  cumulative: string;
  trades: number;
  profitable: number;
  losing: number;
  flat: number;
  grossProfit: string;
  grossLoss: string;
  invested: string | null;
  fees: string | null;
  peak: string;
  trough: string;
  drawdown: string;
};

export type PerformanceData = {
  timezone: string;
  dateBasis: 'entry' | 'close';
  kind: 'paper' | 'live' | 'scalp';
  today: string;
  days: PerformanceDay[];
  pending: number;
  excluded: { invalidDate: number; invalidProfitLoss: number; duplicates: number };
};

export type PerformanceRange = 'month' | '7d' | '30d' | 'all';
export type ChartPoint = { date: string; time: number; daily: number; cumulative: number; trades: number };
