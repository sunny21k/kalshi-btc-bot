import type { BotCommand, EntryPriceRange, BotPreferences } from '../types/bots';
import type { DashboardStats, ResultSync } from '../types/dashboard';
import type { ReplayResponse, ReplayWindow } from '../types/replay';

type SyncResponse = { resultSync?: ResultSync; error?: string };

async function requestJson<T>(path: string, fallbackError: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options);
  const result = await response.json() as T & { message?: string; error?: string };
  if (!response.ok) throw new Error(result.message || result.error || fallbackError);
  return result;
}

function postJson<T>(path: string, body: object, fallbackError: string): Promise<T> {
  return requestJson<T>(path, fallbackError, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function fetchDashboardStats() {
  return requestJson<DashboardStats>('/api/stats', 'Could not load dashboard');
}

export function fetchTradeReplay(botId: string, tradeId: string, refresh = false, signal?: AbortSignal, window: ReplayWindow = 'entry') {
  const query = new URLSearchParams({ botId, tradeId, ...(refresh ? { refresh: '1' } : {}), window });
  return requestJson<ReplayResponse>(`/api/trades/replay?${query}`, 'Could not load trade replay', { signal });
}

export function fetchResultSync() {
  return requestJson<ResultSync>('/api/results/status', 'Could not check results update');
}

export function startResultSync() {
  return postJson<SyncResponse>('/api/results/refresh', {}, 'Could not update results');
}

export function cancelResultSync() {
  return postJson<SyncResponse>('/api/results/cancel', {}, 'Could not stop results refresh');
}

export function saveBotSettings(botId: string, settings: BotPreferences) {
  return postJson<{ ok: boolean; settings: BotPreferences }>('/api/bots/settings', { botId, settings }, 'Could not save bot settings');
}

export function sendBotAction(botId: string, action: BotCommand, tradeBudget?: string, dailyLiveOrderLimit?: string, entryPriceRange?: EntryPriceRange | null, expectedSettingsFingerprint?: string) {
  return postJson<{ message?: string; error?: string }>('/api/bots/' + action, {
    botId,
    ...(action === 'start' && tradeBudget !== undefined ? { tradeBudget } : {}),
    ...(action === 'start' && dailyLiveOrderLimit !== undefined ? { dailyLiveOrderLimit } : {}),
    ...(action === 'start' && entryPriceRange !== undefined ? { entryPriceRange } : {}),
    ...(action === 'start' && expectedSettingsFingerprint !== undefined ? { expectedSettingsFingerprint } : {}),
  }, 'Bot action failed');
}
