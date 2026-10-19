import type { DashboardTrade } from '../types/dashboard';

export const countOpenTrades = (trades: DashboardTrade[]): number =>
  trades.filter((trade) => trade.status === 'OPEN' || trade.status === 'TARGET_1').length;
