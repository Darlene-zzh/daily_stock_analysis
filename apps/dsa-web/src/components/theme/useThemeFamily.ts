import { useContext } from 'react';
import { DEFAULT_FAMILY } from './familyTheme';
import { FamilyThemeContext, type FamilyThemeContextValue } from './familyThemeContext';

export function useThemeFamily(): FamilyThemeContextValue {
  const ctx = useContext(FamilyThemeContext);
  if (!ctx) {
    throw new Error('useThemeFamily must be used within a FamilyThemeProvider');
  }
  return ctx;
}

/**
 * Non-throwing variant — returns DEFAULT_FAMILY when called outside a
 * FamilyThemeProvider. Use this in shared leaf components (e.g. EmptyState)
 * that must also render correctly in tests that don't mount the provider.
 */
export function useThemeFamilyOptional(): Pick<FamilyThemeContextValue, 'family'> {
  const ctx = useContext(FamilyThemeContext);
  return { family: ctx?.family ?? DEFAULT_FAMILY };
}
