/** Locale-aware formatters — everything is India-first (en-IN, ₹, lakh/crore). */

const INR = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 });
const NUM = new Intl.NumberFormat('en-IN');

export function inr(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return INR.format(n);
}

/** ₹1.2 Cr / ₹45.5 L / ₹12.3K — the way Indian business teams actually talk. */
export function inrCompact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e7) return `${sign}₹${trim(abs / 1e7)} Cr`;
  if (abs >= 1e5) return `${sign}₹${trim(abs / 1e5)} L`;
  if (abs >= 1e3) return `${sign}₹${trim(abs / 1e3)}K`;
  return `${sign}₹${Math.round(abs)}`;
}

/** 12,34,567 grouping. */
export function num(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return NUM.format(n);
}

/** 1.2 Cr / 45.5 L / 12.3K for plain counts (followers, listeners). */
export function compact(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e7) return `${trim(abs / 1e7)} Cr`;
  if (abs >= 1e5) return `${trim(abs / 1e5)} L`;
  if (abs >= 1e3) return `${trim(abs / 1e3)}K`;
  return String(Math.round(abs));
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return '—';
  return `${n.toFixed(digits)}%`;
}

export function score(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toFixed(1);
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.round(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d < 30 ? `${d}d ago` : new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function dateIN(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-IN', opts);
}

export function greeting(now = new Date()): string {
  const h = Number(new Intl.DateTimeFormat('en-IN', { hour: 'numeric', hour12: false, timeZone: 'Asia/Kolkata' }).format(now));
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

function trim(v: number): string {
  return v >= 100 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, '');
}
