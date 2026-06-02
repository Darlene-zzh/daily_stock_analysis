import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FamilyThemeProvider } from '../../theme/FamilyThemeProvider';
import { EmptyState } from '../EmptyState';

describe('EmptyState cute variant', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('shows mascot when family is cute', () => {
    window.localStorage.setItem('dsa-theme-family', 'cute');
    render(
      <FamilyThemeProvider>
        <EmptyState title="还没有分析记录" />
      </FamilyThemeProvider>,
    );
    expect(screen.getByText('🍡')).toBeInTheDocument();
  });

  it('no mascot for non-cute family', () => {
    window.localStorage.setItem('dsa-theme-family', 'premium');
    render(
      <FamilyThemeProvider>
        <EmptyState title="还没有分析记录" />
      </FamilyThemeProvider>,
    );
    expect(screen.queryByText('🍡')).not.toBeInTheDocument();
  });

  it('renders without a provider (no mascot, no crash)', () => {
    render(<EmptyState title="还没有分析记录" />);
    expect(screen.getByText('还没有分析记录')).toBeInTheDocument();
    expect(screen.queryByText('🍡')).not.toBeInTheDocument();
  });
});
