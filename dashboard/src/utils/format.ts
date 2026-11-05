export const profitTone = (value: number) => value > 0 ? 'money-positive' : value < 0 ? 'money-negative' : 'muted-heading';

export const moneyClass = (value: string) => Number(value || 0) >= 0 ? 'money-positive' : 'money-negative';

export const fmtPct = (value: number | null) => value === null ? 'N/A' : `${value.toFixed(2)}%`;

export const shortId = (value?: string) => value ? value.replace(/^paper-|^live-|^scalp-/, '').slice(0, 8) : '';

export const fmtDateTime = (value?: string) => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
};

export function tableMoney(value?: string, signed = false) {
  if (value === undefined || value === null || value.trim() === '') return '--';
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  return amount.toLocaleString('en-US', {
    style: 'currency', currency: 'USD', signDisplay: signed ? 'exceptZero' : 'auto',
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  });
}
