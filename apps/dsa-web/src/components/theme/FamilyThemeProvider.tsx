import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import {
  DEFAULT_FAMILY,
  FAMILY_STORAGE_KEY,
  applyFamilyToDocument,
  readStoredFamily,
  type ThemeFamily,
} from './familyTheme';

type FamilyThemeContextValue = {
  family: ThemeFamily;
  setFamily: (family: ThemeFamily) => void;
};

const FamilyThemeContext = createContext<FamilyThemeContextValue | null>(null);

export const FamilyThemeProvider = ({ children }: { children: ReactNode }) => {
  const [family, setFamilyState] = useState<ThemeFamily>(() =>
    typeof window === 'undefined' ? DEFAULT_FAMILY : readStoredFamily(window.localStorage)
  );

  const setFamily = useCallback((next: ThemeFamily) => {
    setFamilyState(next);
    try {
      window.localStorage.setItem(FAMILY_STORAGE_KEY, next);
    } catch {
      /* private mode / blocked storage — keep in-memory only */
    }
    applyFamilyToDocument(next, document.documentElement);
  }, []);

  useEffect(() => {
    applyFamilyToDocument(family, document.documentElement);
  }, [family]);

  const value = useMemo(() => ({ family, setFamily }), [family, setFamily]);

  return <FamilyThemeContext.Provider value={value}>{children}</FamilyThemeContext.Provider>;
};

export function useThemeFamily(): FamilyThemeContextValue {
  const ctx = useContext(FamilyThemeContext);
  if (!ctx) {
    throw new Error('useThemeFamily must be used within a FamilyThemeProvider');
  }
  return ctx;
}
