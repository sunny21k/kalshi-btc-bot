import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react';
import type { RuleDraft } from '../../lib/botSettings';

export function EntryRuleEditor({ rule, index, botId, total, onChange, onRemove, onMove }: {
  rule: RuleDraft; index: number; botId: string; total: number;
  onChange: (rule: RuleDraft) => void; onRemove: () => void; onMove: (direction: -1 | 1) => void;
}) {
  const field = (key: 'maxMinutesLeft' | 'minBtcDistance' | 'minPercent' | 'maxPercent', label: string, min: string, max?: string) => (
    <label className="rule-field" htmlFor={`${rule.id}-${key}`}><span>{label}</span>
      <input id={`${rule.id}-${key}`} type="number" inputMode="decimal" step="0.01" min={min} max={max}
        value={rule[key]} onChange={event => onChange({ ...rule, [key]: event.target.value })} />
    </label>
  );
  return <section className={`entry-rule-editor ${rule.enabled ? '' : 'entry-rule-disabled'}`} aria-label={`Rule ${index + 1}: ${rule.name}`}>
    <div className="entry-rule-toolbar">
      <label><input type="checkbox" checked={rule.enabled} onChange={event => onChange({ ...rule, enabled: event.target.checked })} /> Rule {index + 1} · {rule.enabled ? 'Enabled' : 'Disabled'}</label>
      <div>
        <button type="button" disabled={index === 0} aria-label={`Move rule ${index + 1} up`} onClick={() => onMove(-1)}><ArrowUp size={14} /></button>
        <button type="button" disabled={index === total - 1} aria-label={`Move rule ${index + 1} down`} onClick={() => onMove(1)}><ArrowDown size={14} /></button>
        <button type="button" className="money-negative" aria-label={`Remove rule ${index + 1}`} onClick={onRemove}><Trash2 size={14} /></button>
      </div>
    </div>
    <div className="entry-rule-fields">
      <label className="rule-field" htmlFor={`${rule.id}-name`}><span>Rule name</span><input id={`${rule.id}-name`} maxLength={60} value={rule.name} onChange={event => onChange({ ...rule, name: event.target.value })} /></label>
      <label className="rule-field" htmlFor={`${rule.id}-side`}><span>Buy side</span><select id={`${rule.id}-side`} value={rule.side} onChange={event => onChange({ ...rule, side: event.target.value as RuleDraft['side'] })}>
        {botId !== 'btc15_paper' && <><option value="BOTH">YES or NO</option><option value="YES">YES only</option></>}<option value="NO">NO only</option>
      </select></label>
      {field('maxMinutesLeft', 'Minutes left · at most', '.01', '15')}
      {field('minBtcDistance', 'BTC distance ($) · at least', '0', '10000000')}
      {field('minPercent', 'Minimum entry (%)', '.01', '99.99')}
      {field('maxPercent', 'Maximum entry (%)', '.01', '99.99')}
    </div>
    <label className="entry-rule-direction"><input type="checkbox" checked={rule.requireDirection} onChange={event => onChange({ ...rule, requireDirection: event.target.checked })} /> Require 3 consecutive BTC moves in the buy direction</label>
  </section>;
}
