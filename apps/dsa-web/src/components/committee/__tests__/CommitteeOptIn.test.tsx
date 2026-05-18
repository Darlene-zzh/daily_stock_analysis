import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { CommitteeOptIn } from '../CommitteeOptIn';

describe('CommitteeOptIn', () => {
  it('starts collapsed when the toggle is off', () => {
    render(
      <CommitteeOptIn
        enabled={false}
        rounds={2}
        onEnabledChange={() => undefined}
        onRoundsChange={() => undefined}
      />,
    );

    // Disclosure summary is always visible.
    expect(
      screen.getByText('Advanced — Investment Committee (preview)'),
    ).toBeInTheDocument();
    // Body is hidden until the disclosure is opened.
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('auto-opens when the toggle is already on (state persists across mount)', () => {
    render(
      <CommitteeOptIn
        enabled
        rounds={2}
        onEnabledChange={() => undefined}
        onRoundsChange={() => undefined}
      />,
    );

    // When enabled, the body is rendered immediately so the round picker is visible.
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.getByRole('radiogroup', { name: /debate rounds/i })).toBeInTheDocument();
  });

  it('renders cost hint matching the backend formula (6 + 2*N + 2)', () => {
    const { rerender } = render(
      <CommitteeOptIn
        enabled
        rounds={1}
        onEnabledChange={() => undefined}
        onRoundsChange={() => undefined}
      />,
    );

    expect(screen.getByTestId('committee-cost-hint')).toHaveTextContent('~10 extra LLM calls per stock');

    rerender(
      <CommitteeOptIn
        enabled
        rounds={2}
        onEnabledChange={() => undefined}
        onRoundsChange={() => undefined}
      />,
    );
    expect(screen.getByTestId('committee-cost-hint')).toHaveTextContent('~12 extra LLM calls per stock');

    rerender(
      <CommitteeOptIn
        enabled
        rounds={3}
        onEnabledChange={() => undefined}
        onRoundsChange={() => undefined}
      />,
    );
    expect(screen.getByTestId('committee-cost-hint')).toHaveTextContent('~14 extra LLM calls per stock');
  });

  it('invokes onEnabledChange when the switch toggles', () => {
    const onEnabledChange = vi.fn();
    render(
      <CommitteeOptIn
        enabled={false}
        rounds={2}
        onEnabledChange={onEnabledChange}
        onRoundsChange={() => undefined}
      />,
    );

    // Open the disclosure so the switch is in the tree.
    fireEvent.click(screen.getByRole('button', {
      name: /Advanced — Investment Committee/,
    }));

    fireEvent.click(screen.getByRole('switch'));
    expect(onEnabledChange).toHaveBeenCalledWith(true);
  });

  it('invokes onRoundsChange when a round option is selected', () => {
    const onRoundsChange = vi.fn();
    render(
      <CommitteeOptIn
        enabled
        rounds={2}
        onEnabledChange={() => undefined}
        onRoundsChange={onRoundsChange}
      />,
    );

    fireEvent.click(screen.getByRole('radio', { name: '3' }));
    expect(onRoundsChange).toHaveBeenCalledWith(3);
  });

  it('disables interactive controls while disabled', () => {
    render(
      <CommitteeOptIn
        enabled
        rounds={2}
        onEnabledChange={() => undefined}
        onRoundsChange={() => undefined}
        disabled
      />,
    );

    expect(screen.getByRole('switch')).toBeDisabled();
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toBeDisabled();
    }
  });

  it('disables the round picker when the toggle is off', () => {
    render(
      <CommitteeOptIn
        enabled={false}
        rounds={2}
        onEnabledChange={() => undefined}
        onRoundsChange={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole('button', {
      name: /Advanced — Investment Committee/,
    }));

    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toBeDisabled();
    }
  });
});
