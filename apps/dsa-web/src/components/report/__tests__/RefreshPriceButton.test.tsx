import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { RefreshPriceButton } from '../RefreshPriceButton';
import { stocksApi } from '../../../api/stocks';

vi.mock('../../../api/stocks', () => ({
  stocksApi: {
    getQuote: vi.fn(),
  },
}));

describe('RefreshPriceButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an enabled button by default', () => {
    render(<RefreshPriceButton stockCode="NVDA" onQuote={vi.fn()} />);
    expect(screen.getByRole('button', { name: /刷新/i })).toBeEnabled();
  });

  it('calls stocksApi.getQuote with the stock code on click', async () => {
    const user = userEvent.setup();
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      stockCode: 'NVDA',
      currentPrice: 226.13,
      asOf: '2026-05-24T10:00:00Z',
    });
    const onQuote = vi.fn();
    render(<RefreshPriceButton stockCode="NVDA" onQuote={onQuote} />);

    await user.click(screen.getByRole('button', { name: /刷新/i }));

    await waitFor(() => {
      expect(stocksApi.getQuote).toHaveBeenCalledWith('NVDA');
      expect(onQuote).toHaveBeenCalledWith({
        price: 226.13,
        asOf: '2026-05-24T10:00:00Z',
      });
    });
  });

  it('shows loading state while the request is in flight', async () => {
    const user = userEvent.setup();
    let resolveFn: ((value: unknown) => void) | undefined;
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise((resolve) => {
        resolveFn = resolve;
      }),
    );
    render(<RefreshPriceButton stockCode="NVDA" onQuote={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: /刷新/i }));
    expect(screen.getByRole('button')).toBeDisabled();

    resolveFn!({
      stockCode: 'NVDA',
      currentPrice: 226.13,
      asOf: '2026-05-24T10:00:00Z',
    });
    await waitFor(() => expect(screen.getByRole('button')).toBeEnabled());
  });

  it('exposes an error to onError callback when the request fails', async () => {
    const user = userEvent.setup();
    const err = new Error('boom');
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockRejectedValueOnce(err);
    const onError = vi.fn();
    render(
      <RefreshPriceButton stockCode="NVDA" onQuote={vi.fn()} onError={onError} />,
    );
    await user.click(screen.getByRole('button', { name: /刷新/i }));
    await waitFor(() => expect(onError).toHaveBeenCalledWith(err));
  });

  it('does not call onQuote when the request fails', async () => {
    const user = userEvent.setup();
    (stocksApi.getQuote as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('boom'),
    );
    const onQuote = vi.fn();
    render(
      <RefreshPriceButton stockCode="NVDA" onQuote={onQuote} onError={vi.fn()} />,
    );
    await user.click(screen.getByRole('button', { name: /刷新/i }));
    await waitFor(() => expect(onQuote).not.toHaveBeenCalled());
  });

  it('renders nothing when stockCode is empty', () => {
    const { container } = render(
      <RefreshPriceButton stockCode="" onQuote={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
