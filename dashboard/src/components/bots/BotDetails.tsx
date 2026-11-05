import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import type { BotRules } from '../../types/bots';
import { PopupCard } from '../layout/PopupCard';

export function BotDetails({ rules, name }: { rules?: BotRules; name: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="bot-details">
      <button type="button" className="bot-details-trigger" aria-haspopup="dialog" aria-expanded={open}
        aria-label={`${name} trading rules`} onClick={() => setOpen(true)}>
        Bot Details <ArrowUpRight size={14} aria-hidden="true" />
      </button>
      {open && <PopupCard title="Bot Details" subtitle={name} closeLabel="Close bot details" onClose={() => setOpen(false)}>
        <BotRulesContent rules={rules} />
      </PopupCard>}
    </div>
  );
}

export function BotRulesContent({ rules }: { rules?: BotRules }) {
  return (
      <div className="bot-details-content">
        {!rules ? <p className="bot-details-note">Restart the dashboard server to load this bot’s rule details.</p> : <>
          <div className="bot-details-origin"><span>{rules.source === 'running' ? 'Running bot snapshot' : 'Current code rules'}</span><span>{rules.mode === 'live' ? 'Real money' : 'Paper only'}</span></div>
          {rules.runningWithoutSnapshot && <p className="bot-details-note">This running process has not reported a rule snapshot. These are the current-code rules; restart the bot to load them.</p>}
          {rules.source === 'running' && rules.matchesCurrent === false && <p className="bot-details-note">The current launch configuration differs from this running snapshot. The rules below show what the process reported at startup.</p>}
          {rules.sections.map(group => <section className="bot-rule-section" key={group.title}>
            <h3>{group.title}</h3>
            <dl>{group.items.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.detail}</dd></div>)}</dl>
          </section>)}
        </>}
      </div>
  );
}
