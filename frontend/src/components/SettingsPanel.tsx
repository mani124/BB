import React, { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api/client';
import { Tabs } from './Tabs';
import type { RuntimeSetting, RuntimeSettingsPayload, SettingAuditRow } from '../types';

type Draft = string | boolean;

const asDraft = (s: RuntimeSetting): Draft => (s.type === 'bool' ? Boolean(s.value) : String(s.value));

export const SettingsPanel: React.FC<{ initial?: RuntimeSettingsPayload; initialAudit?: SettingAuditRow[] }> = ({ initial, initialAudit }) => {
  const [data, setData] = useState<RuntimeSettingsPayload | null>(initial ?? null);
  const [audit, setAudit] = useState<SettingAuditRow[]>(initialAudit ?? []);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [group, setGroup] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([apiFetch('/api/settings'), apiFetch('/api/settings/audit?limit=25')]);
      if (!s.ok) throw new Error(String(s.status));
      setData(await s.json());
      if (a.ok) setAudit(await a.json());
      setDrafts({});
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => { if (!initial) void load(); }, [initial, load]);

  const dirty = (s: RuntimeSetting) => s.key in drafts && drafts[s.key] !== asDraft(s);
  const dirtyKeys = data ? data.settings.filter(dirty).map((s) => s.key) : [];

  const save = async () => {
    if (!data || dirtyKeys.length === 0) return;
    const changes: Record<string, Draft | number> = {};
    for (const s of data.settings) {
      if (!dirty(s)) continue;
      const d = drafts[s.key];
      changes[s.key] = s.type === 'int' || s.type === 'float' ? Number(d) : d;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch('/api/settings', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ changes }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(typeof body.detail === 'string' ? body.detail : `Save failed (${res.status})`);
      }
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const reset = async (key: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/settings/${key}/reset`, { method: 'POST' });
      if (!res.ok) throw new Error(`Reset failed (${res.status})`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reset failed');
    } finally {
      setBusy(false);
    }
  };

  if (failed && !data) return <div className="desk-panel p-6 text-center text-xs desk-muted">Could not load settings.</div>;
  if (!data) return <div className="desk-panel p-6 text-center text-xs desk-muted">Loading settings...</div>;

  const control = (s: RuntimeSetting) => {
    const d = s.key in drafts ? drafts[s.key] : asDraft(s);
    const set = (v: Draft) => setDrafts((p) => ({ ...p, [s.key]: v }));
    if (s.type === 'bool') {
      return <input type="checkbox" className="h-5 w-5" style={{ accentColor: 'var(--accent)' }} aria-label={s.label} checked={Boolean(d)} onChange={(e) => set(e.target.checked)} />;
    }
    if (s.choices.length > 0) {
      return (
        <select className="desk-input" aria-label={s.label} value={String(d)} onChange={(e) => set(e.target.value)}>
          {s.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      );
    }
    return (
      <input
        className="desk-input desk-num" aria-label={s.label} value={String(d)}
        type={s.type === 'time' ? 'time' : s.type === 'str' ? 'text' : 'number'}
        min={s.min ?? undefined} max={s.max ?? undefined} step={s.type === 'int' ? 1 : 'any'}
        onChange={(e) => set(e.target.value)}
      />
    );
  };

  const q = query.trim().toLowerCase();
  const activeGroup = group && data.groups.includes(group) ? group : data.groups[0];
  const visible = q
    ? data.settings.filter((x) => `${x.label} ${x.description} ${x.key}`.toLowerCase().includes(q))
    : data.settings.filter((x) => x.group === activeGroup);
  const dirtyIn = (g: string) => data.settings.filter((x) => x.group === g && dirty(x)).length;
  const shownGroups = q ? data.groups.filter((g) => visible.some((x) => x.group === g)) : [activeGroup];

  return (
    <div className="flex flex-col gap-2 lg:flex-1 lg:min-h-0" data-testid="settings-panel">
      <div className="desk-panel shrink-0">
        <div className="desk-ph">
          <h2>Runtime settings</h2>
          <span className="desk-muted text-xs">Changes apply to the next decision. No restart needed. 0 switches a limit off where marked.</span>
          <input
            type="search"
            className="desk-input ml-auto"
            style={{ width: '14rem' }}
            placeholder="Find a setting"
            aria-label="Find a setting"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="button" className="desk-btn solid" disabled={busy || dirtyKeys.length === 0} onClick={save}>
            Save {dirtyKeys.length > 0 ? `${dirtyKeys.length} change${dirtyKeys.length > 1 ? 's' : ''}` : 'changes'}
          </button>
        </div>
        {error && <div className="desk-alert m-3" role="alert">{error}</div>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[15rem_minmax(0,1fr)] gap-3 lg:flex-1 lg:min-h-0">
        <Tabs<string>
          idPrefix="settings"
          orientation="vertical"
          label="Setting groups"
          className="desk-panel p-1.5 flex lg:flex-col gap-0.5 overflow-x-auto lg:overflow-y-auto lg:self-start lg:max-h-full"
          tabClassName="desk-tab justify-between text-left whitespace-nowrap"
          value={activeGroup}
          onChange={(g) => { setGroup(g); setQuery(''); }}
          items={data.groups.map((g) => ({
            id: g,
            name: dirtyIn(g) ? `${g}, ${dirtyIn(g)} unsaved` : g,
            label: (
              <>
                <span>{g}</span>
                {dirtyIn(g) > 0 && <span className="desk-pill warn desk-num" aria-hidden="true">{dirtyIn(g)}</span>}
              </>
            ),
          }))}
        />

        <div id="settings-panel" role="tabpanel" aria-labelledby={`settings-tab-${activeGroup}`} className="flex flex-col gap-3 lg:min-h-0 lg:overflow-y-auto pb-3">
          {q && visible.length === 0 && <div className="desk-panel p-6 text-center text-xs desk-muted">No setting matches "{query}".</div>}
          {shownGroups.map((g) => (
            <section key={g} className="desk-panel" aria-label={g}>
              <div className="desk-ph"><h3>{g}</h3></div>
              <div className="overflow-x-auto">
                <table className="desk-table">
                  <tbody>
                    {visible.filter((x) => x.group === g).map((s) => (
                      <tr key={s.key}>
                        <td style={{ whiteSpace: 'normal', minWidth: 220 }}>
                          <div className="font-medium">{s.label}{dirty(s) && <span className="desk-pill warn ml-2">unsaved</span>}</div>
                          <div className="desk-muted text-xs">{s.description}</div>
                        </td>
                        <td style={{ width: 170 }}>
                          <div className="flex items-center gap-2">{control(s)}{s.unit && <span className="desk-muted text-xs">{s.unit}</span>}</div>
                          {s.zero_disables && Number(s.value) === 0 && <span className="desk-pill warn">off</span>}
                        </td>
                        <td className="desk-muted text-xs">default {String(s.default)}</td>
                        <td className="r">
                          {s.overridden && (
                            <button type="button" className="desk-btn sm" disabled={busy} onClick={() => reset(s.key)} aria-label={`Reset ${s.label}`}>
                              Reset
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}

          {!q && (
            <section className="desk-panel" aria-label="Change history">
              <div className="desk-ph"><h3>Recent changes</h3></div>
              {audit.length === 0 ? <div className="p-4 text-xs desk-muted">No changes yet.</div> : (
                <div className="overflow-x-auto">
                  <table className="desk-table">
                    <thead><tr><th scope="col">When</th><th scope="col">Setting</th><th scope="col">From</th><th scope="col">To</th><th scope="col">By</th></tr></thead>
                    <tbody>
                      {audit.map((a, i) => (
                        <tr key={i}><td className="desk-num">{a.changed_at}</td><td>{a.key}</td><td className="desk-num">{a.old_value}</td><td className="desk-num">{a.new_value}</td><td>{a.actor}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
};
