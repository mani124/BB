import { apiFetch } from './client';
import type { DashboardBook, DashboardChart, DashboardSession, DashboardTrade, DashboardTradeDetail, DashboardWatch } from '../types/dashboard';

export async function fetchDashboardWatch(): Promise<DashboardWatch> {
  const response = await apiFetch('/api/dashboard/watch');
  if (!response.ok) throw new Error(`Dashboard watch failed (${response.status})`);
  return response.json() as Promise<DashboardWatch>;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  if (!response.ok) throw new Error(`Dashboard request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export const fetchDashboardTrades = (): Promise<DashboardTrade[]> => getJson('/api/dashboard/trades');
export const fetchDashboardSession = (day: string): Promise<DashboardSession> => getJson(`/api/dashboard/session?day=${encodeURIComponent(day)}`);
export const fetchDashboardTradeDetail = (trade: DashboardTrade): Promise<DashboardTradeDetail> =>
  getJson(`/api/dashboard/trades/${trade.book}/${encodeURIComponent(trade.source_id)}`);
export const fetchDashboardTradeChart = (trade: DashboardTrade): Promise<DashboardChart> =>
  getJson(`/api/dashboard/trades/${trade.book}/${encodeURIComponent(trade.source_id)}/chart`);

export async function closeTrade(book: DashboardBook, sourceId: string): Promise<void> {
  if (book !== 'paper') throw new Error(`Single-position close is unavailable for ${book}`);
  const response = await apiFetch(`/api/paper/close/${encodeURIComponent(sourceId)}`, { method: 'POST' });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === 'string' ? body.detail : `Close failed (${response.status})`);
  }
}
