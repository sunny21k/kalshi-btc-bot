import type { BotStatus, EntryPriceRange } from '../types/bots';

export type EntryPriceDraft = { useDefaults: boolean; min: string; max: string };

export function pricePercent(price: string): string {
  return String(Number((Number(price) * 100).toFixed(2)));
}

export function entryPriceDraft(bot?: BotStatus): EntryPriceDraft {
  const bands = bot?.entryPriceDefaults ?? [];
  return {
    useDefaults: !bot?.entryPriceRange,
    min: bot?.entryPriceRange ? pricePercent(bot.entryPriceRange.min) : bands.length ? pricePercent(String(Math.min(...bands.map(band => Number(band.min))))) : '75',
    max: bot?.entryPriceRange ? pricePercent(bot.entryPriceRange.max) : bands.length ? pricePercent(String(Math.max(...bands.map(band => Number(band.max))))) : '92',
  };
}

export function entryRangeFromPercent(draft: EntryPriceDraft): EntryPriceRange | null {
  if (draft.useDefaults) return null;
  const values = [draft.min.trim(), draft.max.trim()];
  if (values.some(value => !/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(value) || Number(value) <= 0 || Number(value) >= 100)) {
    throw new Error('Enter entry prices above 0% and below 100%, with at most two decimal places.');
  }
  if (Number(values[0]) > Number(values[1])) throw new Error('Minimum entry price cannot exceed the maximum.');
  return { min: (Number(values[0]) / 100).toFixed(4), max: (Number(values[1]) / 100).toFixed(4) };
}

export function validateEntryPriceRange(range: EntryPriceRange): void {
  if (!range || typeof range !== 'object' || !['min', 'max'].every(key => typeof range[key as keyof EntryPriceRange] === 'string')) throw new Error('Enter a valid entry price range.');
  if ([range.min, range.max].some(value => !/^(?:0(?:\.\d{1,4})?|\.\d{1,4})$/.test(value))) throw new Error('Enter a valid entry price range.');
  const min = Number(range.min), max = Number(range.max);
  if (![min, max].every(value => Number.isFinite(value) && value > 0 && value < 1 && Math.abs(value * 10000 - Math.round(value * 10000)) < 1e-8) || min > max) {
    throw new Error('Enter a valid minimum and maximum entry price, above 0% and below 100%.');
  }
}
