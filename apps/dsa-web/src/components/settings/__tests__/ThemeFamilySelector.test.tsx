import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FamilyThemeProvider } from '../../theme/FamilyThemeProvider';
import { ThemeFamilySelector } from '../ThemeFamilySelector';

describe('ThemeFamilySelector', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('renders four preview cards and selects on click', () => {
    render(
      <FamilyThemeProvider>
        <ThemeFamilySelector />
      </FamilyThemeProvider>
    );
    expect(screen.getAllByRole('radio')).toHaveLength(4);
    fireEvent.click(screen.getByRole('radio', { name: /简约/ }));
    expect(document.documentElement.getAttribute('data-theme')).toBe('minimal');
    expect(screen.getByRole('radio', { name: /简约/ })).toHaveAttribute('aria-checked', 'true');
  });
});
