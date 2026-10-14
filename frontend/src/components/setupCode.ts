// Short "S1".."S8" code for any setup naming scheme the backend emits
// ("Setup 5: Option Chart BB Scalp", "SETUP_5_OPTION_BB_SCALP", "PIN BAR", ...).
export function setupCode(setupType: string | undefined): string {
  const s = (setupType || '').toUpperCase();
  const m = s.match(/SETUP[_ ]?(\d)/);
  if (m) return `S${m[1]}`;
  if (s.includes('SQUEEZE')) return 'S1';
  if (s.includes('WALKING')) return 'S2';
  if (s.includes('REVERSAL') || s.includes('W/M')) return 'S3';
  if (s.includes('ORB') || s.includes('OPENING RANGE')) return 'S4';
  if (s.includes('OPTION')) return 'S5';
  if (s.includes('PIN')) return 'S6';
  if (s.includes('INSIDE')) return 'S7';
  if (s.includes('DIVERGENCE') || s.includes('CLIMAX')) return 'S8';
  return '—';
}
