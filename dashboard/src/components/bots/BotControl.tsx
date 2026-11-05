import React from 'react';
import { Bot, Play, Square } from 'lucide-react';
import type { BotAction, BotStatus } from '../../types/bots';
import { BotDetails } from './BotDetails';
import { botDisplayName } from '../../content/bots';

export function BotControl({ bot, onAction }: { bot?: BotStatus; onAction: BotAction }) {
  const [budget, setBudget] = React.useState(bot?.tradeBudget ?? '1.00');
  const [dailyLimit, setDailyLimit] = React.useState(String(bot?.dailyLiveOrderLimit || 30));
  const [noDailyCap, setNoDailyCap] = React.useState(bot?.dailyLiveOrderLimit === 0);

  React.useEffect(() => {
    setBudget(bot?.tradeBudget ?? '1.00');
  }, [bot?.id, bot?.running, bot?.tradeBudget]);

  React.useEffect(() => {
    setDailyLimit(String(bot?.dailyLiveOrderLimit || 30));
    setNoDailyCap(bot?.dailyLiveOrderLimit === 0);
  }, [bot?.id, bot?.running, bot?.dailyLiveOrderLimit]);

  if (!bot) {
    return (
      <section className="surface-card border p-4">
        <div className="muted-heading text-sm">Restart the dashboard server so this bot appears in the API.</div>
      </section>
    );
  }

  const externalRunning = !bot.running && !!bot.runtime?.processAlive;
  const running = bot.running || externalRunning;
  const hasDailyLimit = bot.mode === 'live' && bot.dailyLiveOrderLimit !== undefined;
  const hasSettings = bot.supportsTradeBudget || hasDailyLimit;
  const name = botDisplayName(bot);

  return (
    <section className="bot-control" aria-label={`${name} ${bot.mode} controls`}>
      <header className="bot-control-heading">
        <div className="bot-control-intro">
          <div className="bot-control-identity">
            <Bot size={17} className="muted-heading shrink-0" />
            <h2>{name}</h2>
          </div>
          <p className="bot-control-description muted-heading">{bot.description}</p>
        </div>
        <div className="bot-control-commands">
          <div className="bot-control-metadata">
            <span className={`bot-control-mode ${bot.mode === 'live' ? 'money-negative' : 'muted-text'}`}>{bot.mode === 'live' ? 'Real money' : 'Paper only'}</span>
            <span className={`bot-control-status ${running ? 'money-positive' : 'muted-text'}`}>
              {bot.running ? `Running ${bot.pid ?? ''}` : externalRunning ? 'Running in terminal' : 'Stopped'}
            </span>
          </div>
          <div className="bot-control-action">
            {externalRunning ? <button className="surface-button border px-3 py-2 text-xs muted-text" disabled title="Stop this bot in the terminal where it was started">Terminal control</button> : bot.running ? (
              <button
                onClick={() => onAction(bot.id, 'stop')}
                className="danger-button inline-flex items-center justify-center gap-2 border px-3 py-2 text-sm font-medium"
              >
                <Square size={15} /> Stop
              </button>
            ) : (
              <button
                onClick={() => onAction(
                  bot.id,
                  'start',
                  bot.supportsTradeBudget ? budget : undefined,
                  hasDailyLimit ? (noDailyCap ? '0' : dailyLimit) : undefined,
                )}
                className={`inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium ${bot.mode === 'live' ? 'live-button' : 'primary-button'}`}
              >
                <Play size={15} /> Start
              </button>
            )}
          </div>
        </div>
      </header>
      <div className={`bot-control-body ${hasSettings ? '' : 'bot-control-body-minimal'}`}>
        {hasSettings && <div className="bot-control-settings">
          {bot.supportsTradeBudget && (
            <div className="bot-control-field">
              <label htmlFor={`${bot.id}-budget`}>Entry budget <span className="sr-only">in dollars, before fees</span></label>
              <div className="bot-budget-input">
                <span aria-hidden="true">$</span>
                <input
                  id={`${bot.id}-budget`}
                  type="number"
                  inputMode="decimal"
                  min="0.01"
                  step="0.01"
                  value={budget}
                  onChange={(event) => setBudget(event.target.value)}
                  disabled={running}
                  aria-describedby={`${bot.id}-budget-help`}
                  className="surface-soft w-full min-w-0 border text-sm tabular-nums disabled:opacity-70"
                />
              </div>
              <p className="bot-field-help" id={`${bot.id}-budget-help`}>Per trade, before fees</p>
            </div>
          )}
          {hasDailyLimit && (
            <div className="bot-control-field">
              <label htmlFor={`${bot.id}-daily-limit`}>Daily order limit <span className="bot-field-unit">UTC</span></label>
              <input
                id={`${bot.id}-daily-limit`}
                type="number"
                inputMode="numeric"
                min="1"
                step="1"
                value={dailyLimit}
                onChange={(event) => setDailyLimit(event.target.value)}
                disabled={running || noDailyCap}
                className="surface-soft w-full min-w-0 border px-3 text-sm tabular-nums disabled:opacity-70"
              />
              <label className="bot-control-checkbox">
                <input
                  type="checkbox"
                  checked={noDailyCap}
                  onChange={(event) => setNoDailyCap(event.target.checked)}
                  disabled={running}
                />
                No daily cap
              </label>
            </div>
          )}
        </div>}
        <details className="bot-control-log muted-text">
          <summary>Log file</summary>
          <code>{bot.logFile}</code>
        </details>
      </div>
      <BotDetails rules={bot.rules} name={name} />
    </section>
  );
}
