import React from 'react';
import { Plus } from 'lucide-react';
import type { BotStatus } from '../../types/bots';
import { saveBotSettings } from '../../api/dashboard';
import { newRule, reorderRule, serializeSettings, settingsDraft } from '../../lib/botSettings';
import { botDisplayName } from '../../content/bots';
import { PopupCard } from '../layout/PopupCard';
import { EntryRuleEditor } from './EntryRuleEditor';
import { EntryPriceSettings } from './EntryPriceSettings';

export function BotSettings({ bot, onClose, onSaved }: { bot: BotStatus; onClose: () => void; onSaved?: () => Promise<void> }) {
  const initial = bot.settings;
  const [draft, setDraft] = React.useState(() => initial ? settingsDraft(initial) : null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const [notice, setNotice] = React.useState('');
  const scalp = bot.id === 'scalp_paper';
  const change: typeof setDraft = value => { setNotice(''); setError(''); setDraft(value); };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!initial || !draft) return;
    setError(''); setNotice('');
    try {
      const settings = serializeSettings(draft, initial);
      setBusy(true);
      const response = await saveBotSettings(bot.id, settings);
      setDraft(settingsDraft(response.settings));
      setNotice('Settings saved. They apply the next time this bot starts.');
      try { await onSaved?.(); }
      catch { setNotice('Settings saved. The dashboard will pick them up on its next refresh.'); }
    } catch (error) { setError(error instanceof Error ? error.message : 'Could not save settings.'); }
    finally { setBusy(false); }
  };

  return <PopupCard title="Bot settings" subtitle={`${botDisplayName(bot)} · ${bot.mode === 'live' ? 'Real money' : 'Paper only'}`} closeLabel="Close bot settings" onClose={onClose}>
    {!draft || !initial ? <p className="bot-details-note">Restart the dashboard server to load editable settings.</p> : <form className="bot-settings-form" onSubmit={save}>
      <p className="settings-intro">Save rules here, then start the bot to use them. A running bot keeps its current rules until you stop and start it.</p>
      {bot.settingsError && <p className="money-negative" role="alert">{bot.settingsError}</p>}
      <fieldset disabled={busy}>
        {(initial.tradeBudget !== undefined || initial.dailyLiveOrderLimit !== undefined) && <div className="settings-sizing">
          {initial.tradeBudget !== undefined && <label className="rule-field" htmlFor={`${bot.id}-settings-budget`}><span>Entry budget ($)</span><input id={`${bot.id}-settings-budget`} type="number" min=".01" step=".01" inputMode="decimal" value={draft.tradeBudget} onChange={event => change({ ...draft, tradeBudget: event.target.value })} /><small>Per trade, before fees</small></label>}
          {initial.dailyLiveOrderLimit !== undefined && <div><label className="rule-field" htmlFor={`${bot.id}-settings-cap`}><span>Daily order limit (UTC)</span><input id={`${bot.id}-settings-cap`} type="number" min="1" step="1" disabled={draft.noDailyCap} value={draft.dailyLimit} onChange={event => change({ ...draft, dailyLimit: event.target.value })} /></label><label className="entry-rule-direction"><input type="checkbox" checked={draft.noDailyCap} onChange={event => change({ ...draft, noDailyCap: event.target.checked })} /> No daily cap</label></div>}
        </div>}
        <div className="settings-rules-heading"><h3>{scalp ? 'Extra entry filters' : 'Entry rules'}</h3><button type="button" className="surface-button" disabled={draft.rules.length >= 20} onClick={() => change({ ...draft, rules: [...draft.rules, newRule(bot.id)] })}><Plus size={14} /> Add rule</button></div>
        <p className="settings-rule-help">{scalp ? 'These filters apply after the candle signal. With no filters, entries use the candle strategy.' : `${bot.id === 'btc15_paper' ? 'Buy NO only when BTC is below the target.' : 'Buy YES above the BTC target or NO below it.'} Rules are checked from top to bottom; the first time, distance, and side match is selected. Its other checks must pass.`}</p>
        {!draft.rules.length && <p className="settings-empty">{scalp ? 'No extra filters. Candle entries remain enabled.' : 'No entry rules. This bot will wait without taking new trades.'}</p>}
        <div className="settings-rule-list">{draft.rules.map((rule, index) => <EntryRuleEditor key={rule.id} botId={bot.id} rule={rule} index={index} total={draft.rules.length}
          onChange={updated => change({ ...draft, rules: draft.rules.map(item => item.id === rule.id ? updated : item) })}
          onRemove={() => change({ ...draft, rules: draft.rules.filter(item => item.id !== rule.id) })}
          onMove={direction => change({ ...draft, rules: reorderRule(draft.rules, index, direction) })} />)}</div>
        {scalp && <EntryPriceSettings bot={bot} value={draft.entryPrices} onChange={value => change({ ...draft, entryPrices: value })} disabled={false} />}
        <p className="settings-rule-help">{scalp ? 'The scalp candle checks, cooldown, cutoff, and exit settings still apply.' : 'The spread, momentum, confirmation, final-30-second cutoff, and one-entry-per-market checks still apply.'}</p>
      </fieldset>
      <div className="settings-feedback" aria-live="polite">{error && <p className="money-negative" role="alert">{error}</p>}{notice && <p className="money-positive" role="status">{notice}</p>}</div>
      <footer className="settings-actions"><button type="button" className="surface-button" disabled={busy || !bot.settingsDefaults} onClick={() => { if (bot.settingsDefaults) { setDraft(settingsDraft(bot.settingsDefaults)); setError(''); setNotice('Defaults loaded. Press Save settings to keep them.'); } }}>Restore defaults</button><button type="submit" className="primary-button" disabled={busy}>{busy ? 'Saving…' : 'Save settings'}</button></footer>
    </form>}
  </PopupCard>;
}
