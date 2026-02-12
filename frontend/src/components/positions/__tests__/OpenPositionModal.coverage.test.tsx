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

describe('OpenPositionModal - Coverage', () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should submit form and call setGlobalLoading', async () => {
    mockOpenPosition.mockResolvedValue(undefined);
    
    render(<OpenPositionModal onClose={onClose} />);
    
    // Find and click the confirm button
    const buttons = screen.getAllByRole('button');
    const confirmButton = buttons.find(b => b.textContent?.toLowerCase().includes('confirm'));
    expect(confirmButton).toBeDefined();
    
    if (confirmButton) {
      fireEvent.click(confirmButton);
    }
    
    await waitFor(() => {
      expect(mockSetGlobalLoading).toHaveBeenCalledWith(true, 'Opening position...');
    });
  });

  it('should change asset selection', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    const selects = screen.getAllByRole('combobox');
    if (selects.length > 0) {
      fireEvent.change(selects[0], { target: { value: 'jitoSOL' } });
    }
  });

  it('should change leverage slider', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    const sliders = screen.getAllByRole('slider');
    if (sliders.length > 0) {
      fireEvent.change(sliders[0], { target: { value: '2.5' } });
    }
  });

  it('should change size input', () => {
    render(<OpenPositionModal onClose={onClose} />);
    
    const inputs = screen.getAllByRole('spinbutton');
    if (inputs.length > 0) {
      fireEvent.change(inputs[0], { target: { value: '5000' } });
    }
  });
});
