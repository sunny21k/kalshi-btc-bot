export type ReplayPoint = {
  time: number; timestamp: string; btcPrice: number; ticker: string;
  yesBid: number | null; yesAsk: number | null; noBid: number | null; noAsk: number | null;
  secondsRemaining: number | null; targetPrice: number | null; priceDifference: number | null;
  decision: string; reason: string; strategy: string; source: string; runId: string;
};
export type ReplayData = {
  status: 'ready'; window: ReplayWindow; startTime: number; endTime: number; generatedAt: string;
  entry: { tradeId: string; botId: string; ticker: string; side: string; at: number; timestamp: string;
    entryPrice: number | null; filled: boolean; anchorLabel: string; strategy: string };
  points: ReplayPoint[]; sourceBasis: 'recorded' | 'shared'; notes: string[];
  targetPrice: number | null; targetBasis: 'recorded' | 'inferred';
  coverage: { samples: number; firstAt: string | null; lastAt: string | null; typicalSeconds: number | null; gaps: Array<{ start: number; end: number }> };
};
export type ReplayWindow = 'entry' | 'market';
export type ReplayResponse = ReplayData | { status: 'preparing'; rows: number; files: number; totalFiles: number };
