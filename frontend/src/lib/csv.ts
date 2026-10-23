export interface CsvColumn { key: string; label: string }

const needsQuote = /[",\r\n]/;

function cell(value: unknown): string {
  if (value === null || value === undefined) return '';
  let s = typeof value === 'object' ? JSON.stringify(value) : String(value);
  // Spreadsheet formula injection guard: a leading = + - @ would execute when the file is opened.
  if (typeof value === 'string' && /^[=+\-@]/.test(s)) s = `'${s}`;
  return needsQuote.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** RFC 4180 CSV. Every row is exported with exactly the given columns. */
export function toCsv(rows: Record<string, unknown>[], columns: CsvColumn[]): string {
  const head = columns.map((c) => cell(c.label)).join(',');
  const body = rows.map((r) => columns.map((c) => cell(r[c.key])).join(','));
  return [head, ...body].join('\r\n');
}

export function downloadCsv(name: string, csv: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
