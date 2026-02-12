import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToastContainer } from '../ToastContainer';

const mockRemoveToast = vi.fn();

vi.mock('../../../stores', () => ({
  useUIStore: () => ({
    toasts: [
      { id: '1', message: 'Success message', type: 'success' as const },
      { id: '2', message: 'Error message', type: 'error' as const },
    ],
    removeToast: mockRemoveToast,
  }),
}));

describe('ToastContainer', () => {
  beforeEach(() => {
    mockRemoveToast.mockClear();
  });

  it('should render toasts', () => {
    render(<ToastContainer />);
    
    expect(screen.getByText('Success message')).toBeInTheDocument();
    expect(screen.getByText('Error message')).toBeInTheDocument();
  });

  it('should render success toast with correct styling', () => {
    render(<ToastContainer />);
    
    const successToast = screen.getByText('Success message').parentElement;
    expect(successToast).toHaveClass('bg-green-600');
  });

  it('should render error toast with correct styling', () => {
    render(<ToastContainer />);
    
    const errorToast = screen.getByText('Error message').parentElement;
    expect(errorToast).toHaveClass('bg-red-600');
  });

  it('should call removeToast when close button is clicked', () => {
    render(<ToastContainer />);
    
    const closeButtons = screen.getAllByLabelText('Close');
    fireEvent.click(closeButtons[0]);
    
    expect(mockRemoveToast).toHaveBeenCalledWith('1');
  });

  it('should have correct ARIA role', () => {
    render(<ToastContainer />);
    
    const alerts = screen.getAllByRole('alert');
    expect(alerts).toHaveLength(2);
  });
});
