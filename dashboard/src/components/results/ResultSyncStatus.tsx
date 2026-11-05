import { AlertTriangle, RefreshCw } from 'lucide-react';
import type { ResultSync } from '../../types/dashboard';
import { fmtDateTime } from '../../utils/format';

export function ResultSyncStatus({ sync, pending, error }: { sync?: ResultSync; pending: boolean; error: string }) {
  const busy = pending || sync?.running;
  const summary = sync?.summary;
  const failed = error || sync?.error;
  if (!busy && !failed && !sync?.completedAt) return null;

  return (
    <div className="min-w-0 text-sm" role="status" aria-live="polite">
      <div className={`flex items-start gap-2 ${failed || summary?.errorCount ? 'money-negative' : 'muted-heading'}`}>
        {busy ? <RefreshCw size={15} className="mt-0.5 shrink-0 animate-spin" /> : failed || summary?.errorCount ? <AlertTriangle size={15} className="mt-0.5 shrink-0" /> : null}
        <span className="min-w-0 break-words">
          {busy ? `${sync?.stopping ? 'Stopping after the current check...' : 'Updating fills, fees, and settlements...'}${summary?.checked !== undefined ? ` ${summary.checked} check${summary.checked === 1 ? '' : 's'} finished.` : ''}${error ? ` ${error}` : ''}` : failed ? `Results update failed: ${failed}` : summary
            ? `${summary.stopped ? 'Refresh stopped' : 'Results checked'} ${fmtDateTime(sync?.completedAt ?? '')}. Settled: ${summary.liveSettled} live, ${summary.paperSettled + summary.dualPaperSettled + (summary.directionPaperSettled ?? 0)} paper. New predictions: ${summary.predictionsRecorded}.${summary.stopped ? ' Saved updates kept; unchecked trades are unchanged.' : ''}${summary.errorCount ? ` ${summary.errorCount} checks need attention.` : ''}`
            : 'Results updated.'}
        </span>
      </div>
      {!busy && !!summary?.errors.length && (
        <details className="muted-heading mt-2">
          <summary className="cursor-pointer">Refresh errors</summary>
          <ul className="mt-2 grid gap-1">
            {summary.errors.map((item, index) => <li className="break-words" key={index}>{item.stage}: {item.message}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
