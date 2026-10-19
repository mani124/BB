import { apiFetch } from './client';
import type { DashboardWatch } from '../types/dashboard';

export async function fetchDashboardWatch(): Promise<DashboardWatch> {
  const response = await apiFetch('/api/dashboard/watch');
  if (!response.ok) throw new Error(`Dashboard watch failed (${response.status})`);
  return response.json() as Promise<DashboardWatch>;
}
