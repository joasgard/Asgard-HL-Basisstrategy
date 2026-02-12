import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Skeleton, SkeletonCard, SkeletonStats } from '../Skeleton';

describe('Skeleton', () => {
  it('should render with default classes', () => {
    render(<Skeleton />);
    
    const skeleton = screen.getByRole('presentation');
    expect(skeleton).toBeInTheDocument();
    expect(skeleton).toHaveClass('animate-pulse', 'bg-gray-700', 'rounded');
  });

  it('should apply custom height and width', () => {
    render(<Skeleton height="h-10" width="w-20" />);
    
    const skeleton = screen.getByRole('presentation');
    expect(skeleton).toHaveClass('h-10', 'w-20');
  });

  it('should apply custom className', () => {
    render(<Skeleton className="custom-class" />);
    
    const skeleton = screen.getByRole('presentation');
    expect(skeleton).toHaveClass('custom-class');
  });
});

describe('SkeletonCard', () => {
  it('should render card structure', () => {
    render(<SkeletonCard />);
    
    const skeletons = screen.getAllByRole('presentation');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

describe('SkeletonStats', () => {
  it('should render 4 stat skeletons', () => {
    render(<SkeletonStats />);
    
    const skeletons = screen.getAllByRole('presentation');
    expect(skeletons.length).toBeGreaterThanOrEqual(8); // 4 cards with 2 skeletons each
  });
});
