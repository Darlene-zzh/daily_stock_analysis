import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { FamilyThemeProvider } from '../FamilyThemeProvider';
import { useThemeFamily } from '../useThemeFamily';
import { FamilyToggle } from '../FamilyToggle';

function Probe() {
  const { family } = useThemeFamily();
  return <span data-testid="current">{family}</span>;
}

describe('FamilyToggle', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('lists four families and switches on click', () => {
    render(
      <FamilyThemeProvider>
        <FamilyToggle />
        <Probe />
      </FamilyThemeProvider>
    );
    fireEvent.click(screen.getByRole('button', { name: /主题风格/ }));
    expect(screen.getAllByRole('menuitem')).toHaveLength(4);
    fireEvent.click(screen.getByRole('menuitem', { name: /可爱/ }));
    expect(screen.getByTestId('current')).toHaveTextContent('cute');
  });
});
