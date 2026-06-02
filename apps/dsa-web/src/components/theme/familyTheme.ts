export type ThemeFamily = 'classic' | 'cute' | 'minimal' | 'premium';

export const THEME_FAMILIES: ThemeFamily[] = ['classic', 'cute', 'minimal', 'premium'];
export const DEFAULT_FAMILY: ThemeFamily = 'premium';
export const FAMILY_STORAGE_KEY = 'dsa-theme-family';

export function isThemeFamily(value: unknown): value is ThemeFamily {
  return typeof value === 'string' && (THEME_FAMILIES as string[]).includes(value);
}

export function readStoredFamily(storage: Pick<Storage, 'getItem'>): ThemeFamily {
  try {
    const value = storage.getItem(FAMILY_STORAGE_KEY);
    return isThemeFamily(value) ? value : DEFAULT_FAMILY;
  } catch {
    return DEFAULT_FAMILY;
  }
}

export function applyFamilyToDocument(family: ThemeFamily, root: HTMLElement): void {
  root.setAttribute('data-theme', family);
}
