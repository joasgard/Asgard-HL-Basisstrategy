import { useState, useCallback } from 'react';

interface LeverageSliderProps {
  value: number;
  onChange: (value: number) => void;
}

export function LeverageSlider({ value, onChange }: LeverageSliderProps) {
  const [inputValue, setInputValue] = useState(value.toFixed(1));
  const [isValid, setIsValid] = useState(true);

  const handleSliderChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = parseFloat(e.target.value);
    onChange(newValue);
    setInputValue(newValue.toFixed(1));
    setIsValid(true);
  }, [onChange]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = e.target.value;
    setInputValue(rawValue);
    
    const numValue = parseFloat(rawValue);
    if (!isNaN(numValue) && numValue >= 1.1 && numValue <= 4.0) {
      onChange(Math.round(numValue * 10) / 10);
      setIsValid(true);
    } else {
      setIsValid(false);
    }
  }, [onChange]);

  const handleInputBlur = useCallback(() => {
    const numValue = parseFloat(inputValue);
    if (isNaN(numValue) || numValue < 1.1) {
      setInputValue('1.1');
      onChange(1.1);
    } else if (numValue > 4.0) {
      setInputValue('4.0');
      onChange(4.0);
    } else {
      const rounded = Math.round(numValue * 10) / 10;
      setInputValue(rounded.toFixed(1));
      onChange(rounded);
    }
    setIsValid(true);
  }, [inputValue, onChange]);

  return (
    <div className="flex-1">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium">Desired Leverage</h2>
        <div className="flex items-center gap-1">
          <input
            type="number"
            min="1.1"
            max="4.0"
            step="0.1"
            value={inputValue}
            onChange={handleInputChange}
            onBlur={handleInputBlur}
            className={`w-24 text-3xl font-bold bg-transparent border-b-2 outline-none text-right transition-colors ${
              isValid ? 'text-blue-400 border-blue-400/50 focus:border-blue-400' : 'text-red-400 border-red-400'
            }`}
            title="Type value between 1.1 and 4.0"
          />
          <span className="text-3xl font-bold text-blue-400">x</span>
        </div>
      </div>

      <input
        type="range"
        min="1.1"
        max="4"
        step="0.1"
        value={value}
        onChange={handleSliderChange}
        className="leverage-slider w-full"
        title="Leverage range: 1.1x to 4x"
      />

      <div className="flex justify-between text-sm text-gray-500 mt-3">
        <span>1.1x</span>
        <span>2x</span>
        <span>3x</span>
        <span>4x</span>
      </div>
    </div>
  );
}
