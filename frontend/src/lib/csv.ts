/** Client-side CSV export (RFC 4180 quoting, UTF-8 BOM so Excel renders ₹ and Indic names). */
export type CsvCell = string | number | boolean | null | undefined;

const esc = (v: CsvCell) => {
  if (v == null) return '';
  let s = String(v);
  // Neutralise spreadsheet formula injection from data-driven strings.
  if (typeof v === 'string' && /^[=+\-@]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv(header: string[], rows: CsvCell[][]): string {
  return [header, ...rows].map(r => r.map(esc).join(',')).join('\r\n');
}

export function downloadCsv(filename: string, header: string[], rows: CsvCell[][]) {
  const blob = new Blob(['﻿', toCsv(header, rows)], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
