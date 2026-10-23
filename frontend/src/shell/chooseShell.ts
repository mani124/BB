export type ShellKind = 'legacy' | 'dock';

export const SHELL_STORAGE_KEY = 'bb_shell';

interface StorageLike { getItem(k: string): string | null; setItem(k: string, v: string): void }

/** `?shell=` wins and is remembered; otherwise the remembered choice; the default stays `legacy` until cutover. */
export function chooseShell(search: string, storage: StorageLike | null | undefined): ShellKind {
  let fromQuery: string | null = null;
  try { fromQuery = new URLSearchParams(search).get('shell'); } catch { /* malformed query */ }
  if (fromQuery === 'legacy' || fromQuery === 'dock') {
    try { storage?.setItem(SHELL_STORAGE_KEY, fromQuery); } catch { /* storage unavailable */ }
    return fromQuery;
  }
  try {
    const saved = storage?.getItem(SHELL_STORAGE_KEY);
    if (saved === 'legacy' || saved === 'dock') return saved;
  } catch { /* storage unavailable */ }
  return 'legacy';
}
