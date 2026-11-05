const side = { total: 1, settled: 1, winRate: 100, profitLoss: '16.5057' };
const row = {
  timestamp: '2026-11-04T14:10:05+00:00', trade_id: 'paper-example-trade',
  ticker: 'KXBTC15M-26NOV040915-15', side: 'NO', entry_price: '0.8500',
  strategy_name: 'strong_5m_50', actual_result: 'NO', profit_loss: '16.5057',
  filled_count: '117.00', submitted_count: '117', fill_status: 'FILLED', fees_paid: '1.0443',
};

export function dashboardFixture() {
  const trade = () => ({
    total: 1, settled: 1, unsettled: 0, wins: 1, losses: 0, winRate: 100,
    totalInvested: '99.4500', totalTraded: '99.4500', profitLoss: '16.5057', roi: 16.6,
    yes: { ...side }, no: { ...side }, byStrategy: { strong_5m_50: { ...side } }, byTime: {},
    recent: [{ ...row }],
  });
  const ids = ['btc15_paper', 'btc15_dual_paper', 'btc15_live', 'btc15_dual_live', 'scalp_paper'];
  return {
    paper: trade(), dualPaper: trade(), live: trade(), dualLive: trade(),
    scalp: {
      total: 1, closed: 1, open: 0, wins: 1, losses: 0, winRate: 100,
      totalInvested: '0.8500', profitLoss: '0.0020', peakProfit: '0.0300', byReason: { 'trailing giveback': 1 },
      recent: [{
        ...row, trade_id: 'scalp-example-trade', event: 'CLOSE', exit_price: '0.8520', profit_loss: '0.0020',
        opened_at: '2026-11-04T14:10:05+00:00', closed_at: '2026-11-04T14:10:15+00:00', reason: 'trailing giveback',
      }],
    },
    shadow: { total: 1, decisions: { WAIT: 1 }, blockedReasons: { 'more than 5 minutes left': 1 }, recent: [{ ...row, decision: 'WAIT', reason: 'more than 5 minutes left' }] },
    bots: ids.map((id) => ({
      id, name: id, mode: id.includes('live') ? 'live' : 'paper', description: 'Example bot settings',
      running: false, pid: null, returnCode: null, logFile: `data/bot_logs/${id}.log`,
      supportsTradeBudget: id !== 'scalp_paper', tradeBudget: '100.00',
      ...(id.includes('live') ? { dailyLiveOrderLimit: 30 } : {}),
      runtime: { state: 'stopped', processAlive: false, managed: true, blockers: ['Bot is stopped. Start it to evaluate new entries.'] },
    })),
  };
}
