import { createContext } from 'react';
import type { ThemeFamily } from './familyTheme';

export type FamilyThemeContextValue = {
  family: ThemeFamily;
  setFamily: (family: ThemeFamily) => void;
};

export const FamilyThemeContext = createContext<FamilyThemeContextValue | null>(null);
