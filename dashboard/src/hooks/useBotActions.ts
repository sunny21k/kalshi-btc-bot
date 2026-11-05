import React from 'react';
import { sendBotAction } from '../api/dashboard';
import type { BotCommand, BotStatus, EntryPriceRange } from '../types/bots';
import { botDisplayName } from '../content/bots';
import { pricePercent, validateEntryPriceRange } from '../lib/entryPrices';

export function useBotActions(bots: BotStatus[], load: () => Promise<void>) {
  const [actionError, setActionError] = React.useState('');

  const botAction = React.useCallback(async (botId: string, action: BotCommand, tradeBudget?: string, dailyLiveOrderLimit?: string, entryPriceRange?: EntryPriceRange | null) => {
    const selectedBot = bots.find((bot) => bot.id === botId);
    setActionError('');
    if (action === 'start' && entryPriceRange !== undefined && entryPriceRange !== null) {
      try { validateEntryPriceRange(entryPriceRange); }
      catch (error) { setActionError(error instanceof Error ? error.message : 'Invalid entry price range.'); return; }
    }
    if (action === 'start' && selectedBot?.supportsTradeBudget) {
      const value = tradeBudget?.trim() ?? '';
      if (!/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(value) || !/[1-9]/.test(value)) {
        setActionError('Enter a positive dollar budget with at most two decimal places.');
        return;
      }
    }
    if (action === 'start' && selectedBot?.mode === 'live' && dailyLiveOrderLimit !== undefined) {
      const value = dailyLiveOrderLimit.trim();
      if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value))) {
        setActionError('Enter a whole-number daily order limit, or select No daily cap.');
        return;
      }
    }
    const budgetLabel = `$${tradeBudget?.trim() ?? selectedBot?.tradeBudget ?? '1.00'}`;
    const dailyLimit = Number(dailyLiveOrderLimit ?? selectedBot?.dailyLiveOrderLimit);
    const dailyLimitLabel = Number.isNaN(dailyLimit)
      ? 'Daily order limit not reported by the server.'
      : dailyLimit === 0
        ? 'NO DAILY ORDER CAP.'
        : `Up to ${dailyLimit} live order attempts per UTC day, counted across both live bots.`;
    const selectedRange = entryPriceRange === undefined ? selectedBot?.entryPriceRange : entryPriceRange;
    const rangeLabel = selectedRange ? `Entry price range: ${pricePercent(selectedRange.min)}–${pricePercent(selectedRange.max)}% for every entry rule.` : selectedBot?.settings ? 'Entry prices: saved per-rule settings.' : 'Entry prices: strategy defaults.';
    const enabledRules = selectedBot?.settings?.entryRules.filter(rule => rule.enabled);
    const rulesLabel = enabledRules ? `Saved rules (${enabledRules.length} enabled): ${enabledRules.map(rule => `${rule.name}: up to ${rule.maxMinutesLeft}m, at least $${rule.minBtcDistance}, ${pricePercent(rule.priceRange.min)}–${pricePercent(rule.priceRange.max)}%`).join('; ') || 'none; no new entries'}.` : '';
    if (action === 'start' && selectedBot?.mode === 'live' && !window.confirm(
      `Start ${botDisplayName(selectedBot)} with REAL MONEY? Up to ${budgetLabel} entry cost PER TRADE, plus exchange fees. Whole contracts. ${rangeLabel} ${rulesLabel} ${dailyLimitLabel} No daily loss stop. One attempt per market.`,
    )) return;

    try {
      await sendBotAction(botId, action, tradeBudget, dailyLiveOrderLimit, entryPriceRange, action === 'start' ? selectedBot?.settingsFingerprint : undefined);
      await load();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Bot action failed');
    }
  }, [bots, load]);

  return { botAction, actionError };
}
