"use client";

import { useState } from "react";

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
  const [isApproving, setIsApproving] = useState(false);

  const handleApprove = () => {
    setIsApproving(true);
    onApprove();
  };

  const handleReject = () => {
    setIsApproving(false);
    onReject();
  };

  return (
    <div className="rounded-xl border-2 border-yellow-600 bg-gradient-to-br from-yellow-900/40 to-amber-900/40 p-5 shadow-lg">
      {/* Header */}
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-yellow-500 shadow-md">
          <span className="text-xl">⚠️</span>
        </div>
        <div>
          <p className="font-bold text-yellow-200">
            Write Query Approval Required
          </p>
          <p className="text-xs text-yellow-300">
            The AI wants to modify your database
          </p>
        </div>
      </div>

      {/* SQL preview */}
      <div className="mb-4 overflow-hidden rounded-xl border-2 border-yellow-700 bg-gray-900 shadow-md">
        <div className="bg-gray-800 px-4 py-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">Proposed Query</span>
        </div>
        <pre className="overflow-x-auto px-4 py-4 text-xs leading-relaxed text-green-300">
          <code>{sql.trim()}</code>
        </pre>
      </div>

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={handleApprove}
          disabled={deciding}
          className="flex-1 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm font-bold text-white shadow-md transition-all hover:shadow-lg hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {deciding && isApproving ? (
            <span className="flex items-center justify-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Running…
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Allow Query
            </span>
          )}
        </button>
        <button
          onClick={handleReject}
          disabled={deciding}
          className="flex-1 rounded-xl border-2 border-gray-600 bg-gray-700 px-5 py-3 text-sm font-bold text-gray-200 shadow-md transition-all hover:border-gray-500 hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {deciding && !isApproving ? (
            <span className="flex items-center justify-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-gray-200 border-t-transparent" />
              Processing…
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              Reject
            </span>
          )}
        </button>
      </div>
    </div>
  );
}
