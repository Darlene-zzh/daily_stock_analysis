import { describe, expect, it } from 'vitest';
import {
  DEFAULT_FAMILY,
  FAMILY_STORAGE_KEY,
  THEME_FAMILIES,
  isThemeFamily,
  readStoredFamily,
} from '../familyTheme';

describe('familyTheme', () => {
  it('exposes the four families and premium default', () => {
    expect(THEME_FAMILIES).toEqual(['premium', 'cute', 'minimal', 'classic']);
    expect(DEFAULT_FAMILY).toBe('premium');
  });

  it('isThemeFamily guards unknown values', () => {
    expect(isThemeFamily('cute')).toBe(true);
    expect(isThemeFamily('neon')).toBe(false);
    expect(isThemeFamily(null)).toBe(false);
  });

  it('readStoredFamily returns stored valid family', () => {
    const storage = { getItem: (k: string) => (k === FAMILY_STORAGE_KEY ? 'minimal' : null) };
    expect(readStoredFamily(storage)).toBe('minimal');
  });

  it('readStoredFamily falls back to default on garbage or throw', () => {
    expect(readStoredFamily({ getItem: () => 'bogus' })).toBe('premium');
    expect(readStoredFamily({ getItem: () => { throw new Error('blocked'); } })).toBe('premium');
  });
});
