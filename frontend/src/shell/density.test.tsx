import { describe, it, expect, beforeEach } from 'vitest';
import { setDensity } from './Chrome';
import { appStore, resetAppStore } from '../data/appStore';

beforeEach(() => { localStorage.clear(); resetAppStore(); });

describe('density', () => {
  it('persists, updates the store and tags the document', () => {
    setDensity('comfortable');
    expect(appStore.getState().ui.density).toBe('comfortable');
    expect(localStorage.getItem('bb_density')).toBe('comfortable');
    expect(document.documentElement.dataset.density).toBe('comfortable');
  });
  it('is read back as the initial density', () => {
    localStorage.setItem('bb_density', 'comfortable');
    resetAppStore();
    expect(appStore.getState().ui.density).toBe('comfortable');
  });
});
