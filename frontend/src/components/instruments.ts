// Index underlyings, mirroring INDEX_SYMBOLS in backend/app/services/strategy_engine.py.
export const INDEX_SYMBOLS = new Set([
  'NIFTY 50', 'NIFTY', 'NIFTY BANK', 'BANKNIFTY', 'BANK NIFTY', 'FINNIFTY',
  'NIFTY FINANCIAL SERVICES', 'SENSEX', 'MIDCPNIFTY',
]);

export const isIndexSymbol = (symbol: string | undefined): boolean =>
  INDEX_SYMBOLS.has((symbol ?? '').toUpperCase());
