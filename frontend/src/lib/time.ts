const IST = 'Asia/Kolkata';

export interface IstParts { year: number; month: number; day: number; hour: number; minute: number; second: number; weekday: number }

const fmt = new Intl.DateTimeFormat('en-GB', {
  timeZone: IST, hour12: false, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short',
});
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function toDate(d: string | number | Date): Date {
  return d instanceof Date ? d : new Date(d);
}

/** Wall-clock parts of an instant in Indian Standard Time. weekday: 0 = Sunday. */
export function toIst(d: string | number | Date): IstParts {
  const parts = fmt.formatToParts(toDate(d));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '0';
  const hour = Number(get('hour')) % 24;
  return {
    year: Number(get('year')), month: Number(get('month')), day: Number(get('day')),
    hour, minute: Number(get('minute')), second: Number(get('second')),
    weekday: WEEKDAYS.indexOf(get('weekday')),
  };
}

const p2 = (n: number) => String(n).padStart(2, '0');

export function formatIst(d: string | number | Date, kind: 'time' | 'date' | 'datetime' = 'time'): string {
  if (Number.isNaN(toDate(d).getTime())) return '';
  const t = toIst(d);
  const date = `${t.year}-${p2(t.month)}-${p2(t.day)}`;
  const time = `${p2(t.hour)}:${p2(t.minute)}:${p2(t.second)}`;
  return kind === 'time' ? time : kind === 'date' ? date : `${date} ${time}`;
}

/** Whole seconds between `asOf` (epoch ms) and now. Never negative. */
export function ageSeconds(asOf: number, now: number = Date.now()): number {
  return Math.max(0, Math.round((now - asOf) / 1000));
}

/** NSE cash session: 09:15 to 15:30 IST, Monday to Friday (holidays are not modelled). */
export function marketSession(now: Date = new Date()): 'pre-open' | 'open' | 'closed' | 'weekend' {
  const t = toIst(now);
  if (t.weekday === 0 || t.weekday === 6) return 'weekend';
  const minutes = t.hour * 60 + t.minute;
  if (minutes < 9 * 60 + 15) return 'pre-open';
  if (minutes < 15 * 60 + 30) return 'open';
  return 'closed';
}

/** Today's date in IST as YYYY-MM-DD. */
export function istToday(now: Date = new Date()): string {
  return formatIst(now, 'date');
}
