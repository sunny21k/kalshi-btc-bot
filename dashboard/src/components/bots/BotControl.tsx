import React from 'react';
import { Bot, Play, Settings, Square } from 'lucide-react';
import type { BotAction, BotStatus } from '../../types/bots';
import { BotDetails } from './BotDetails';
import { BotSettings } from './BotSettings';
import { botDisplayName } from '../../content/bots';

export function BotControl({ bot, onAction, onSettingsSaved }: { bot?: BotStatus; onAction: BotAction; onSettingsSaved?: () => Promise<void> }) {
  const [settingsOpen, setSettingsOpen] = React.useState(false);
  if (!bot) return <section className="surface-card border p-4"><div className="muted-heading text-sm">Restart the dashboard server so this bot appears in the API.</div></section>;

  const externalRunning = !bot.running && !!bot.runtime?.processAlive;
  const running = bot.running || externalRunning;
  const name = botDisplayName(bot);
  const budget = bot.settings?.tradeBudget ?? bot.tradeBudget ?? '1.00';
  const cap = bot.settings?.dailyLiveOrderLimit ?? bot.dailyLiveOrderLimit;
  const count = bot.settings?.entryRules.filter(rule => rule.enabled).length;
  const start = () => onAction(bot.id, 'start', bot.supportsTradeBudget ? budget : undefined,
    cap !== undefined ? String(cap) : undefined,
    bot.supportsEntryPriceRange ? bot.entryPriceRange ?? null : undefined);

  return <section className="bot-control" aria-label={`${name} ${bot.mode} controls`}>
    <header className="bot-control-heading">
      <div className="bot-control-intro">
        <div className="bot-control-identity"><Bot size={17} className="muted-heading shrink-0" /><h2>{name}</h2></div>
        <p className="bot-control-description muted-heading">{bot.description}</p>
      </div>
      <div className="bot-control-commands">
        <div className="bot-control-metadata">
          <span className={`bot-control-mode ${bot.mode === 'live' ? 'money-negative' : 'muted-text'}`}>{bot.mode === 'live' ? 'Real money' : 'Paper only'}</span>
          <span className={`bot-control-status ${running ? 'money-positive' : 'muted-text'}`}>{bot.running ? `Running ${bot.pid ?? ''}` : externalRunning ? 'Running in terminal' : 'Stopped'}</span>
        </div>
        <div className="bot-control-action">
          {externalRunning ? <button className="surface-button border px-3 py-2 text-xs muted-text" disabled title="Stop this bot in the terminal where it was started">Terminal control</button> : bot.running ? (
            <button onClick={() => onAction(bot.id, 'stop')} className="danger-button inline-flex items-center justify-center gap-2 border px-3 py-2 text-sm font-medium"><Square size={15} /> Stop</button>
          ) : <button onClick={start} disabled={!!bot.settingsError} className={`inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium ${bot.mode === 'live' ? 'live-button' : 'primary-button'}`}><Play size={15} /> Start</button>}
        </div>
      </div>
    </header>
    <div className="bot-saved-summary muted-text">
      {count !== undefined && <span>{bot.id === 'scalp_paper' ? count ? `${count} entry filters` : '5s / 15s candles' : `${count} enabled ${count === 1 ? 'rule' : 'rules'}`}</span>}
      {bot.supportsTradeBudget && <span>${Number(budget).toFixed(2)} per entry</span>}
      {cap !== undefined && <span>{cap === 0 ? 'No daily cap' : `${cap} orders / day`}</span>}
      {running && <span>Saved settings apply on next start</span>}
    </div>
    {bot.settingsError && <p className="money-negative bot-field-help" role="alert">{bot.settingsError}</p>}
    <div className="bot-control-tools">
      <BotDetails rules={bot.rules} name={name} />
      <button type="button" className="bot-settings-trigger" aria-haspopup="dialog" aria-expanded={settingsOpen}
        onClick={() => setSettingsOpen(true)}><Settings size={14} /> Settings</button>
      <details className="bot-control-log muted-text"><summary>Log file</summary><code>{bot.logFile}</code></details>
    </div>
    {settingsOpen && <BotSettings bot={bot} onClose={() => setSettingsOpen(false)} onSaved={onSettingsSaved} />}
  </section>;
}
