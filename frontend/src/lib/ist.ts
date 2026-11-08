/** India-time date helpers: every date a user sees is IST, regardless of the browser's zone. */
export const IST = 'Asia/Kolkata';

export function istDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }): string {
  if (!iso) return '—';
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00+05:30` : iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-IN', { ...opts, timeZone: IST });
}
export function istTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', timeZone: IST });
}
/** YYYY-MM-DD of an instant in India. */
export const istKey = (iso: string | Date) => new Date(iso).toLocaleDateString('en-CA', { timeZone: IST });
export const istToday = () => istKey(new Date());
/** Whole days from today (IST) to the event's IST day; negative when past. */
export function daysFromToday(iso: string): number {
  const a = Date.parse(`${istKey(iso)}T00:00:00Z`), b = Date.parse(`${istToday()}T00:00:00Z`);
  return Math.round((a - b) / 86_400_000);
}
