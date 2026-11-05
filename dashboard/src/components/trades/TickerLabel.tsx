export function TickerLabel({ value }: { value?: string }) {
  return <abbr className="trade-ticker" title={value}>{value?.replace(/^KXBTC15M-/, '') || '--'}</abbr>;
}
