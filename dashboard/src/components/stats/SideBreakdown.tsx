import type { SideStats } from '../../types/trades';
import { fmtPct, moneyClass, tableMoney } from '../../utils/format';

export function SideBreakdown({ yes, no, live }: { yes: SideStats; no: SideStats; live?: boolean }) {
  return (
    <div className="side-breakdown-scroll">
      <table className="side-breakdown" aria-label="Performance by purchased side">
        <thead>
          <tr><th scope="col">Side</th><th scope="col" className="table-number">Trades</th><th scope="col" className="table-number">Win rate</th><th scope="col" className="table-number">{live ? 'Net P/L' : 'P/L'}</th></tr>
        </thead>
        <tbody>
          {([['YES', yes], ['NO', no]] as const).map(([side, stats]) => (
            <tr key={side}>
              <th scope="row">{side}</th>
              <td className="table-number">{stats.total}</td>
              <td className="table-number">{fmtPct(stats.winRate)}</td>
              <td className={`table-number ${moneyClass(stats.profitLoss)}`}>{tableMoney(stats.profitLoss, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
