import { useContext } from 'react';
import { FamilyThemeContext, type FamilyThemeContextValue } from './familyThemeContext';

export function useThemeFamily(): FamilyThemeContextValue {
  const ctx = useContext(FamilyThemeContext);
  if (!ctx) {
    throw new Error('useThemeFamily must be used within a FamilyThemeProvider');
  }
  return ctx;
}
