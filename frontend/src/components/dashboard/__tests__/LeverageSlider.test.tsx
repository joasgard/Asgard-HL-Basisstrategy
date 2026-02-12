import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { LeverageSlider } from '../LeverageSlider';

describe('LeverageSlider', () => {
  const defaultProps = {
    value: 3.0,
    onChange: vi.fn(),
  };

  it('should render with default value', () => {
    render(<LeverageSlider {...defaultProps} />);
    
    expect(screen.getByText('Desired Leverage')).toBeInTheDocument();
    expect(screen.getByDisplayValue('3.0')).toBeInTheDocument();
  });

  it('should call onChange when slider changes', () => {
    const onChange = vi.fn();
    render(<LeverageSlider {...defaultProps} onChange={onChange} />);
    
    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '2.5' } });
    
    expect(onChange).toHaveBeenCalledWith(2.5);
  });

  it('should display leverage markers', () => {
    render(<LeverageSlider {...defaultProps} />);
    
    expect(screen.getByText('1.1x')).toBeInTheDocument();
    expect(screen.getByText('2x')).toBeInTheDocument();
    expect(screen.getByText('3x')).toBeInTheDocument();
    expect(screen.getByText('4x')).toBeInTheDocument();
  });

  it('should show validation error for invalid input', () => {
    render(<LeverageSlider {...defaultProps} />);
    
    const input = screen.getByDisplayValue('3.0');
    fireEvent.change(input, { target: { value: '0.5' } });
    
    expect(input).toHaveClass('text-red-400');
  });

  it('should clamp value on blur for out of range input', () => {
    const onChange = vi.fn();
    render(<LeverageSlider {...defaultProps} onChange={onChange} />);
    
    const input = screen.getByDisplayValue('3.0');
    fireEvent.change(input, { target: { value: '10' } });
    fireEvent.blur(input);
    
    expect(onChange).toHaveBeenCalledWith(4.0);
  });
});
