import { ChevronDown } from 'lucide-react';
import type { BotRules } from '../../types/bots';

export function BotDetails({ rules, name }: { rules?: BotRules; name: string }) {
  return (
    <details className="bot-details" aria-label={`${name} trading rules`}>
      <summary><span>Bot Details</span><ChevronDown size={14} aria-hidden="true" /></summary>
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
    </details>
  );
}
