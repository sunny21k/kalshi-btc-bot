import React from 'react';
import type { PerformanceData } from '../../types/performance';

const PerformancePanel = React.lazy(() => import('./PerformancePanel').then((module) => ({ default: module.PerformancePanel })));

export function BotPerformance({ data }: { data?: PerformanceData }) {
  return (
    <React.Suspense fallback={<section className="performance-section performance-loading" role="status">Loading performance...</section>}>
      <PerformancePanel data={data} />
    </React.Suspense>
  );
}
