import type { BotStatus } from '../../types/bots';
import { pricePercent, type EntryPriceDraft } from '../../lib/entryPrices';

export function EntryPriceSettings({ bot, value, onChange, disabled }: {
  bot: BotStatus; value: EntryPriceDraft; onChange: (value: EntryPriceDraft) => void; disabled: boolean;
}) {
  const help = `${bot.id}-entry-price-help`;
  return (
    <fieldset className="entry-price-settings" disabled={disabled} aria-describedby={help}>
      <legend>Entry price range</legend>
      <label className="bot-control-checkbox entry-price-defaults">
        <input type="checkbox" checked={value.useDefaults} onChange={event => onChange({ ...value, useDefaults: event.target.checked })} />
        Use strategy defaults
      </label>
      {value.useDefaults ? <p className="entry-price-default-bands muted-text">
        {(bot.entryPriceDefaults ?? []).map(band => <span key={band.label}>{band.label}: {pricePercent(band.min)}–{pricePercent(band.max)}%</span>)}
      </p> : <div className="entry-price-inputs">
        {(['min', 'max'] as const).map(key => <div className="bot-control-field" key={key}>
          <label htmlFor={`${bot.id}-entry-${key}`}>{key === 'min' ? 'Minimum (%)' : 'Maximum (%)'}</label>
          <input id={`${bot.id}-entry-${key}`} type="number" min="0.01" max="99.99" step="0.01" inputMode="decimal"
            value={value[key]} onChange={event => onChange({ ...value, [key]: event.target.value })}
            className="surface-soft w-full min-w-0 border px-3 text-sm tabular-nums disabled:opacity-70" />
        </div>)}
      </div>}
      <p className="bot-field-help" id={help}>{value.useDefaults ? 'Uses each filter’s price band, or the default scalp band when no filters are configured.' : 'Overrides the price band for every scalp entry. Other checks still apply.'} {disabled ? 'Stop the bot to edit.' : 'Saved with settings; applied on next start.'}</p>
      {bot.entryPriceError && <p className="money-negative bot-field-help" role="alert">{bot.entryPriceError}</p>}
    </fieldset>
  );
}
