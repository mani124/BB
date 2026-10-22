import { describe, it, expect } from 'vitest';
import { toCsv } from './csv';

describe('toCsv', () => {
  const cols = [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }];
  it('quotes commas, quotes and newlines', () => {
    expect(toCsv([{ a: 'x,y', b: 'say "hi"' }, { a: 'l1\nl2', b: 3 }], cols)).toBe('A,B\r\n"x,y","say ""hi"""\r\n"l1\nl2",3');
  });
  it('guards formula injection', () => {
    expect(toCsv([{ a: '=SUM(A1)', b: '+1' }, { a: '-2+3', b: '@x' }], cols)).toBe("A,B\r\n'=SUM(A1),'+1\r\n'-2+3,'@x");
  });
  it('leaves numbers (including negatives) alone and blanks null', () => {
    expect(toCsv([{ a: -5, b: null }], cols)).toBe('A,B\r\n-5,');
  });
});
