import type { Page } from '@playwright/test';

/**
 * Layouts are stored on the server, so one spec's changes would reach the next. Before a spec: delete custom layouts and
 * save every built-in workspace's default over its saved copy (built-ins cannot be deleted). Runs inside the dev server's
 * origin so it can import the real presets.
 */
export async function resetServerLayouts(page: Page, key: string): Promise<void> {
  await page.goto('/popout.html');
  await page.evaluate(async (k) => {
    const headers = { 'X-Dashboard-Capability': k, 'Content-Type': 'application/json' };
    const { PRESETS } = await import('/src/features/layouts/presets.ts');
    const list = (await (await fetch('/api/ui/layouts', { headers })).json()) as { name: string }[];
    for (const l of list) if (l.name.startsWith('custom:')) await fetch(`/api/ui/layouts/${encodeURIComponent(l.name)}`, { method: 'DELETE', headers });
    for (const [name, body] of Object.entries(PRESETS)) {
      await fetch(`/api/ui/layouts/${encodeURIComponent(`workspace:${name}`)}`, { method: 'PUT', headers, body: JSON.stringify({ kind: 'workspace', schema_version: 1, body }) });
    }
  }, key);
}
