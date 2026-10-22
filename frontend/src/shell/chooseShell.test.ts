import { describe, it, expect } from 'vitest';
import { chooseShell } from './chooseShell';

const mem = () => { const m: Record<string, string> = {}; return { getItem: (k: string) => m[k] ?? null, setItem: (k: string, v: string) => { m[k] = v; }, m }; };

describe('chooseShell', () => {
  it('defaults to legacy', () => {
    expect(chooseShell('', mem())).toBe('legacy');
  });
  it('?shell= wins and is remembered', () => {
    const s = mem();
    expect(chooseShell('?shell=dock', s)).toBe('dock');
    expect(s.m.bb_shell).toBe('dock');
    expect(chooseShell('', s)).toBe('dock');
    expect(chooseShell('?shell=legacy', s)).toBe('legacy');
    expect(chooseShell('', s)).toBe('legacy');
  });
  it('ignores garbage values', () => {
    expect(chooseShell('?shell=nope', mem())).toBe('legacy');
  });
  it('survives storage that throws or is missing', () => {
    const bad = { getItem() { throw new Error('x'); }, setItem() { throw new Error('x'); } };
    expect(chooseShell('?shell=dock', bad)).toBe('dock');
    expect(chooseShell('', bad)).toBe('legacy');
    expect(chooseShell('', null)).toBe('legacy');
  });
});
