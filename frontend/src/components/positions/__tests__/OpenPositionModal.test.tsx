import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { OpenPositionModal } from '../OpenPositionModal';

const mockOpenPosition = vi.fn();
const mockSetGlobalLoading = vi.fn();

vi.mock('../../../hooks', () => ({
  usePositions: () => ({
    openPosition: mockOpenPosition,
  }),
  useSettings: () => ({
    settings: {
      defaultLeverage: 3.0,
      minPositionSize: 100,
      maxPositionSize: 50000,
    },
  }),
}));

vi.mock('../../../stores', () => ({
  useUIStore: () => ({
    setGlobalLoading: mockSetGlobalLoading,
  }),
}));

describe('OpenPositionModal', () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render modal with title', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    expect(screen.getByText('Open Position')).toBeInTheDocument();
  });

  it('should render asset selector', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    // Check for select element with assets
    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBeGreaterThan(0);
  });

  it('should render leverage slider', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    expect(screen.getByRole('slider')).toBeInTheDocument();
  });

  it('should render size input', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    // Look for number input
    const numberInputs = screen.getAllByRole('spinbutton');
    expect(numberInputs.length).toBeGreaterThan(0);
  });

  it('should call onClose when cancel clicked', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    const cancelButton = screen.getByRole('button', { name: /cancel/i });
    fireEvent.click(cancelButton);
    
    expect(onClose).toHaveBeenCalled();
  });

  it('should submit form with correct values', async () => {
    mockOpenPosition.mockResolvedValue(undefined);
    
    render(<OpenPositionModal onClose={onClose} />);
    
    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    fireEvent.click(confirmButton);
    
    await waitFor(() => {
      expect(mockOpenPosition).toHaveBeenCalledWith('SOL', 3.0, 1000);
    });
  });

  it('should show loading state when submitting', async () => {
    mockOpenPosition.mockImplementation(() => new Promise(() => {}));
    
    render(<OpenPositionModal onClose={onClose} />);
    
    const confirmButton = screen.getByRole('button', { name: /confirm/i });
    fireEvent.click(confirmButton);
    
    await waitFor(() => {
      expect(mockSetGlobalLoading).toHaveBeenCalledWith(true, 'Opening position...');
    });
  });
});
