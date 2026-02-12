import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LeverageSlider } from '../LeverageSlider';

describe('LeverageSlider - Edge Cases', () => {
  it('should handle empty input', () => {
    const onChange = vi.fn();
    render(<LeverageSlider value={3.0} onChange={onChange} />);
    
    const input = screen.getByDisplayValue('3.0');
    fireEvent.change(input, { target: { value: '' } });
    
    // Empty input should show validation error
    expect(input).toHaveClass('text-red-400');
  });

  it('should handle non-numeric input', () => {
    const onChange = vi.fn();
    render(<LeverageSlider value={3.0} onChange={onChange} />);
    
    const input = screen.getByDisplayValue('3.0');
    fireEvent.change(input, { target: { value: 'abc' } });
    
    // Non-numeric should show validation error
    expect(input).toHaveClass('text-red-400');
  });

  it('should clamp to min on blur when below range', () => {
    const onChange = vi.fn();
    render(<LeverageSlider value={3.0} onChange={onChange} />);
    
    const input = screen.getByDisplayValue('3.0');
    fireEvent.change(input, { target: { value: '0.5' } });
    fireEvent.blur(input);
    
    expect(onChange).toHaveBeenCalledWith(1.1);
  });

  it('should clamp to max on blur when above range', () => {
    const onChange = vi.fn();
    render(<LeverageSlider value={3.0} onChange={onChange} />);
    
    const input = screen.getByDisplayValue('3.0');
    fireEvent.change(input, { target: { value: '10' } });
    fireEvent.blur(input);
    
    expect(onChange).toHaveBeenCalledWith(4.0);
  });

  it('should round value to 1 decimal on blur', () => {
    const onChange = vi.fn();
    render(<LeverageSlider value={3.0} onChange={onChange} />);
    
    const input = screen.getByDisplayValue('3.0');
    fireEvent.change(input, { target: { value: '2.55' } });
    fireEvent.blur(input);
    
    expect(onChange).toHaveBeenCalledWith(2.6);
  });

  it('should handle value exactly at max', () => {
    const onChange = vi.fn();
    render(<LeverageSlider value={4.0} onChange={onChange} />);
    
    expect(screen.getByDisplayValue('4.0')).toBeInTheDocument();
  });

  it('should handle value exactly at min', () => {
    const onChange = vi.fn();
    const { container } = render(<LeverageSlider value={1.1} onChange={onChange} />);
    
    // Value should be displayed
    expect(container.textContent).toContain('1.1');
  });

  it('should update input when value prop changes', () => {
    const onChange = vi.fn();
    const { rerender } = render(<LeverageSlider value={2.0} onChange={onChange} />);
    
    expect(screen.getByDisplayValue('2.0')).toBeInTheDocument();
    
    rerender(<LeverageSlider value={3.5} onChange={onChange} />);
    
    // Input should update to reflect new value
    expect(screen.getByDisplayValue('3.5')).toBeInTheDocument();
  });
});
