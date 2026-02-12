import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GlobalLoading } from '../GlobalLoading';

const mockStore = {
  globalLoading: false,
  loadingMessage: '',
};

vi.mock('../../../stores', () => ({
  useUIStore: () => mockStore,
}));

describe('GlobalLoading', () => {
  it('should return null when not loading', () => {
    mockStore.globalLoading = false;
    const { container } = render(<GlobalLoading />);
    expect(container.firstChild).toBeNull();
  });

  it('should render loading spinner when loading', () => {
    mockStore.globalLoading = true;
    mockStore.loadingMessage = '';
    
    const { container } = render(<GlobalLoading />);
    expect(container.firstChild).not.toBeNull();
    
    // Check for spinner
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  it('should display loading message when provided', () => {
    mockStore.globalLoading = true;
    mockStore.loadingMessage = 'Loading data...';
    
    render(<GlobalLoading />);
    expect(screen.getByText('Loading data...')).toBeInTheDocument();
  });
});
