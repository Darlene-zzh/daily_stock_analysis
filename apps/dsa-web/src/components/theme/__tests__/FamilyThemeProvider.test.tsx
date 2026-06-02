import { act, render, renderHook, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FAMILY_STORAGE_KEY } from '../familyTheme';
import { FamilyThemeProvider } from '../FamilyThemeProvider';
import { useThemeFamily } from '../useThemeFamily';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <FamilyThemeProvider>{children}</FamilyThemeProvider>
);

describe('FamilyThemeProvider', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to premium and writes data-theme', () => {
    const { result } = renderHook(() => useThemeFamily(), { wrapper });
    expect(result.current.family).toBe('premium');
    expect(document.documentElement.getAttribute('data-theme')).toBe('premium');
  });

  it('hydrates from localStorage', () => {
    window.localStorage.setItem(FAMILY_STORAGE_KEY, 'cute');
    const { result } = renderHook(() => useThemeFamily(), { wrapper });
    expect(result.current.family).toBe('cute');
    expect(document.documentElement.getAttribute('data-theme')).toBe('cute');
  });

  it('setFamily updates state, storage and document', () => {
    const { result } = renderHook(() => useThemeFamily(), { wrapper });
    act(() => result.current.setFamily('minimal'));
    expect(result.current.family).toBe('minimal');
    expect(window.localStorage.getItem(FAMILY_STORAGE_KEY)).toBe('minimal');
    expect(document.documentElement.getAttribute('data-theme')).toBe('minimal');
  });

  it('throws when used outside provider', () => {
    expect(() => renderHook(() => useThemeFamily())).toThrow(/FamilyThemeProvider/);
  });

  it('renders children', () => {
    render(<FamilyThemeProvider><span>hi</span></FamilyThemeProvider>);
    expect(screen.getByText('hi')).toBeInTheDocument();
  });
});
