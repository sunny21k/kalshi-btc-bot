import type { BotStatus, TabId } from '../types/bots';

export const BOT_NAMES: Record<Exclude<TabId, 'shadow'>, string> = {
  btc15_paper: '15m NO Only',
  btc15_dual_paper: '15m YES/NO',
  btc15_direction_paper: '15m Direction',
  scalp_paper: '5s Scalp',
  btc15_live: '15m Early',
  btc15_dual_live: '15m YES/NO',
};

export const BOT_NAV_GROUPS: Array<{ id: string; label: string; tabs: TabId[] }> = [
  { id: 'paper', label: 'Paper bots', tabs: ['btc15_paper', 'btc15_dual_paper', 'btc15_direction_paper', 'scalp_paper'] },
  { id: 'live', label: 'Live bots', tabs: ['btc15_live', 'btc15_dual_live'] },
  { id: 'activity', label: 'Activity', tabs: ['shadow'] },
];

export function botDisplayName(bot: Pick<BotStatus, 'id' | 'name'>): string {
  return BOT_NAMES[bot.id as keyof typeof BOT_NAMES] ?? bot.name;
}
