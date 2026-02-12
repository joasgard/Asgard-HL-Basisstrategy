interface SkeletonProps {
  className?: string;
  height?: string;
  width?: string;
}

export function Skeleton({ className = '', height = 'h-4', width = 'w-full' }: SkeletonProps) {
  return (
    <div
      role="presentation"
      className={`animate-pulse bg-gray-700 rounded ${height} ${width} ${className}`}
    />
  );
}

export function SkeletonCard() {
  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 space-y-3">
      <div className="flex items-center gap-3">
        <Skeleton height="h-12" width="w-12" className="rounded-lg" />
        <div className="flex-1 space-y-2">
          <Skeleton height="h-4" width="w-24" />
          <Skeleton height="h-3" width="w-32" />
        </div>
      </div>
      <Skeleton height="h-8" width="w-full" />
    </div>
  );
}

export function SkeletonStats() {
  return (
    <div className="grid md:grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <Skeleton height="h-3" width="w-20" className="mb-2" />
          <Skeleton height="h-8" width="w-16" />
        </div>
      ))}
    </div>
  );
}
