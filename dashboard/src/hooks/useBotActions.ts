import React from 'react';
import { sendBotAction } from '../api/dashboard';
import type { BotCommand, BotStatus } from '../types/bots';

export function useBotActions(bots: BotStatus[], load: () => Promise<void>) {
  const [actionError, setActionError] = React.useState('');

  const botAction = React.useCallback(async (botId: string, action: BotCommand, tradeBudget?: string, dailyLiveOrderLimit?: string) => {
    const selectedBot = bots.find((bot) => bot.id === botId);
    setActionError('');
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
    if (action === 'start' && selectedBot?.mode === 'live' && !window.confirm(
      `Start ${selectedBot.name} with REAL MONEY? Up to ${budgetLabel} entry cost PER TRADE, plus exchange fees. Whole contracts. ${dailyLimitLabel} No daily loss stop. One attempt per market.`,
    )) return;

    try {
      await sendBotAction(botId, action, tradeBudget, dailyLiveOrderLimit);
      await load();
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Bot action failed');
    }
  }, [bots, load]);

  return { botAction, actionError };
}
