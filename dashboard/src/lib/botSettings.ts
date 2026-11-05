import type { BotPreferences, EntryRule } from '../types/bots';
import { entryRangeFromPercent, pricePercent, type EntryPriceDraft } from './entryPrices';

export type RuleDraft = Omit<EntryRule, 'priceRange'> & { minPercent: string; maxPercent: string };
export type SettingsDraft = { rules: RuleDraft[]; tradeBudget: string; dailyLimit: string; noDailyCap: boolean; entryPrices: EntryPriceDraft };

export function settingsDraft(settings: BotPreferences): SettingsDraft {
  return {
    rules: settings.entryRules.map(({ priceRange, ...rule }) => ({ ...rule, minPercent: pricePercent(priceRange.min), maxPercent: pricePercent(priceRange.max) })),
    tradeBudget: settings.tradeBudget ?? '1.00', dailyLimit: String(settings.dailyLiveOrderLimit || 30),
    noDailyCap: settings.dailyLiveOrderLimit === 0,
    entryPrices: { useDefaults: !settings.entryPriceRange, min: settings.entryPriceRange ? pricePercent(settings.entryPriceRange.min) : '1', max: settings.entryPriceRange ? pricePercent(settings.entryPriceRange.max) : '99' },
  };
}

export function newRule(botId: string, id = `rule-${crypto.randomUUID()}`): RuleDraft {
  return { id, name: 'New rule', enabled: true, maxMinutesLeft: '4', minBtcDistance: '10',
    side: botId === 'btc15_paper' ? 'NO' : 'BOTH', minPercent: botId === 'scalp_paper' ? '1' : '75',
    maxPercent: botId === 'scalp_paper' ? '99' : '92', requireDirection: false };
}

export function serializeSettings(draft: SettingsDraft, original: BotPreferences): BotPreferences {
  if (draft.rules.length > 20) throw new Error('Use at most 20 entry rules.');
  const seen = new Set<string>();
  const entryRules = draft.rules.map(rule => {
    if (!rule.name.trim() || rule.name.trim().length > 60 || /[\x00-\x1f]/.test(rule.name)) throw new Error('Each rule needs a name of 1–60 characters.');
    if (seen.has(rule.id)) throw new Error('Rule IDs must be unique.');
    seen.add(rule.id);
    for (const [label, raw, min, max] of [['Minutes remaining', rule.maxMinutesLeft, .01, 15], ['BTC distance', rule.minBtcDistance, 0, 10000000]] as const) {
      if (!/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(raw.trim()) || Number(raw) < min || Number(raw) > max) throw new Error(`${label} must be between ${min} and ${max}, with at most two decimal places.`);
    }
    const { minPercent, maxPercent, ...value } = rule;
    return { ...value, name: rule.name.trim(), priceRange: entryRangeFromPercent({ useDefaults: false, min: minPercent, max: maxPercent })! };
  });
  const settings: BotPreferences = { entryRules, entryPriceRange: 'tradeBudget' in original ? null : entryRangeFromPercent(draft.entryPrices) };
  if ('tradeBudget' in original) {
    if (!/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(draft.tradeBudget.trim()) || Number(draft.tradeBudget) <= 0) throw new Error('Enter a positive entry budget with at most two decimal places.');
    settings.tradeBudget = draft.tradeBudget.trim();
  }
  if ('dailyLiveOrderLimit' in original) {
    if (!draft.noDailyCap && (!/^\d+$/.test(draft.dailyLimit.trim()) || !Number.isSafeInteger(Number(draft.dailyLimit)) || Number(draft.dailyLimit) < 1)) throw new Error('Enter a whole-number daily order limit or select No daily cap.');
    settings.dailyLiveOrderLimit = draft.noDailyCap ? 0 : Number(draft.dailyLimit);
  }
  return settings;
}

export function reorderRule(rules: RuleDraft[], index: number, movement: -1 | 1): RuleDraft[] {
  const target = index + movement;
  if (index < 0 || index >= rules.length || target < 0 || target >= rules.length) return rules;
  const next = [...rules];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}
