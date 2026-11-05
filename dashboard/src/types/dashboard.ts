import type { BotStatus } from './bots';
import type { ScalpStats, ShadowStats, TradeStats } from './trades';

export type DashboardStats = {
  paper: TradeStats;
  dualPaper: TradeStats;
  directionPaper: TradeStats;
  live: TradeStats;
  dualLive: TradeStats;
  scalp: ScalpStats;
  shadow: ShadowStats;
  bots: BotStatus[];
  resultSync?: ResultSync;
};

export type ResultSync = {
  running: boolean;
  stopping?: boolean;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  summary: {
    paperSettled: number;
    dualPaperSettled: number;
    directionPaperSettled?: number;
    liveSettled: number;
    predictionsRecorded: number;
    errorCount: number;
    checked?: number;
    stopped?: boolean;
    errors: Array<{ stage: string; message: string }>;
  } | null;
};
