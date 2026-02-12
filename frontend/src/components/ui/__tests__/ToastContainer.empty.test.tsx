import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { ToastContainer } from '../ToastContainer';

vi.mock('../../../stores', () => ({
  useUIStore: () => ({
    toasts: [],
    removeToast: vi.fn(),
  }),
}));

describe('ToastContainer - Empty State', () => {
  it('should return null when no toasts', () => {
    const { container } = render(<ToastContainer />);
    expect(container.firstChild).toBeNull();
  });
});
