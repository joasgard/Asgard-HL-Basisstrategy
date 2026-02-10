export function ActivePositions() {
  // TODO: Fetch actual positions from API
  const positions: unknown[] = [];

  return (
    <div className="bg-gray-800 rounded-xl p-6 border border-gray-700">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-medium">Active Positions</h2>
        <button
          onClick={() => window.location.reload()}
          className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </button>
      </div>

      {positions.length === 0 ? (
        <div className="text-center py-8 text-gray-500">
          <p>No active positions</p>
          <p className="text-sm mt-1">Select leverage and click &quot;Open Position&quot; to start</p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Position cards will be rendered here */}
        </div>
      )}
    </div>
  );
}
