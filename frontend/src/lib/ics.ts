import type { VenueCalendarEvent } from '@/lib/api';

const icsEsc = (t: string) => t.replace(/\\/g, '\\\\').replace(/[,;]/g, m => `\\${m}`).replace(/\r?\n/g, '\\n');
const icsStamp = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
/** RFC 5545 calendar of a venue's tracked events (UTC timestamps, so every calendar app shows them in the viewer's zone). */
export function buildIcs(venueName: string, city: string, events: VenueCalendarEvent[]) {
  const lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//LiveIQ//Venue Calendar//EN', 'CALSCALE:GREGORIAN', `X-WR-CALNAME:${icsEsc(venueName)} (LiveIQ)`];
  for (const e of events) {
    lines.push('BEGIN:VEVENT', `UID:${e.id}@liveiq`, `DTSTAMP:${icsStamp(new Date())}`, `DTSTART:${icsStamp(new Date(e.event_date))}`,
      `SUMMARY:${icsEsc(e.title)}`, `LOCATION:${icsEsc(`${venueName}, ${city}`)}`, `DESCRIPTION:${icsEsc([e.source, e.status].filter(Boolean).join(' · '))}`, 'END:VEVENT');
  }
  lines.push('END:VCALENDAR');
  return lines.join('\r\n');
}
