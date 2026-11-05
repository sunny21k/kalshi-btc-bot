type ErrorDetail = { message: string; type: string; source: string; at: string; active: boolean; recoveredAt?: string | null };
export type BotRules = {
  schemaVersion: number;
  botId: string;
  mode: string;
  fingerprint: string;
  sections: Array<{ title: string; items: Array<{ label: string; detail: string }> }>;
  source: 'running' | 'current';
  matchesCurrent?: boolean;
  runningWithoutSnapshot?: boolean;
};
export type BotRuntime = {
  state: 'healthy' | 'degraded' | 'stale' | 'starting' | 'stopped';
  processAlive: boolean;
  managed: boolean;
  pid?: number;
  stage?: string;
  heartbeatAt?: string;
  heartbeatAgeSeconds?: number | null;
  priceAgeSeconds?: number | null;
  price?: { value: string; at: string } | null;
  market?: {
    ticker?: string | null; at?: string; closeAt?: string | null;
    secondsRemaining?: number | string | null; priceDifference?: string | null;
    yesAsk?: string | null; noAsk?: string | null; spread?: string | null;
  };
  decision?: { action: string; reason: string; side?: string; strategy?: string; at: string } | null;
  blockers: string[];
  dailyAttempts?: number | null;
  dailyLimit?: number | null;
  lastApiError?: ErrorDetail | null;
  lastError?: ErrorDetail | null;
};

export type BotStatus = {
  rules?: BotRules;
  runtime?: BotRuntime;
  id: string;
  name: string;
  mode: string;
  description: string;
  running: boolean;
  pid: number | null;
  returnCode: number | null;
  logFile: string;
  supportsTradeBudget?: boolean;
  tradeBudget?: string | null;
  dailyLiveOrderLimit?: number;
};

export type BotCommand = 'start' | 'stop';
export type BotAction = (botId: string, action: BotCommand, tradeBudget?: string, dailyLiveOrderLimit?: string) => void;

export type TabId = 'btc15_paper' | 'btc15_dual_paper' | 'btc15_direction_paper' | 'btc15_live' | 'btc15_dual_live' | 'scalp_paper' | 'shadow';
