interface ApprovalCardProps {
  sql: string;
  onApprove: () => void;
  onReject: () => void;
  /** True while the /chat/execute request is in flight. */
  deciding: boolean;
}

export default function ApprovalCard({
  sql,
  onApprove,
  onReject,
  deciding,
}: ApprovalCardProps) {
  return (
    <div className="rounded-lg border border-yellow-300 bg-yellow-50 p-4 text-sm">
      {/* Header */}
      <div className="mb-3 flex items-center gap-2">
        <span className="text-base">⚠️</span>
        <p className="font-medium text-yellow-800">
          The AI wants to run a write query. Allow it?
        </p>
      </div>

      {/* SQL preview */}
      <div className="mb-4 overflow-hidden rounded border border-yellow-200 bg-gray-900">
        <pre className="overflow-x-auto px-4 py-3 text-xs text-green-300">
          <code>{sql.trim()}</code>
        </pre>
      </div>

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={onApprove}
          disabled={deciding}
          className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {deciding ? (
            <span className="flex items-center gap-2">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Running…
            </span>
          ) : (
            "Allow"
          )}
        </button>
        <button
          onClick={onReject}
          disabled={deciding}
          className="rounded border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
