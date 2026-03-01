"use client";

import { useState } from "react";
import ResultsTable from "./ResultsTable";
import type { QueryStep } from "@/app/chat/page";

interface QueryStepBlockProps {
  step: QueryStep;
  index: number;
}

const KIND_BADGE: Record<string, { label: string; className: string }> = {
  auto:     { label: "Auto",     className: "bg-gray-100 text-gray-500" },
  approved: { label: "Approved", className: "bg-green-100 text-green-700" },
  rejected: { label: "Rejected", className: "bg-gray-100 text-gray-400 line-through" },
  blocked:  { label: "Blocked",  className: "bg-red-100 text-red-600" },
};

export default function QueryStepBlock({ step, index }: QueryStepBlockProps) {
  const [expanded, setExpanded] = useState(false);

  const kind = step.kind ?? "auto";
  const badge = KIND_BADGE[kind] ?? KIND_BADGE.auto;

  const isRejected = kind === "rejected";
  const hasResults = !step.error && step.columns.length > 0;
  const rowCount = step.rows.length;

  const statusLabel = step.error
    ? kind === "rejected" ? "Not run" : kind === "blocked" ? "Blocked" : "Error"
    : rowCount === 0
    ? "0 rows"
    : `${rowCount} row${rowCount !== 1 ? "s" : ""}`;

  const statusColor = step.error
    ? kind === "rejected"
      ? "text-gray-400"
      : "text-red-500"
    : "text-green-600";

  return (
    <div className={`rounded border bg-white text-xs ${isRejected ? "border-gray-200 opacity-60" : "border-gray-200"}`}>
      {/* Header row */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left hover:bg-gray-50"
      >
        <div className="flex items-center gap-2 min-w-0">
          {/* Kind badge */}
          <span className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${badge.className}`}>
            {badge.label}
          </span>
          {/* SQL preview */}
          <span className={`truncate font-mono text-gray-600 ${isRejected ? "line-through text-gray-400" : ""}`}>
            {step.sql.trim().slice(0, 80)}{step.sql.trim().length > 80 ? "…" : ""}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`font-medium ${statusColor}`}>{statusLabel}</span>
          <span className="text-gray-400">{expanded ? "▲" : "▼"}</span>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-gray-100">
          <div className="bg-gray-900 px-3 py-2">
            <pre className="overflow-x-auto text-xs text-green-300">
              <code>{step.sql.trim()}</code>
            </pre>
          </div>
          <div className="px-3 py-2">
            {step.error ? (
              <div className={`rounded border px-3 py-2 text-xs ${
                kind === "rejected"
                  ? "border-gray-200 bg-gray-50 text-gray-500"
                  : "border-red-200 bg-red-50 text-red-600"
              }`}>
                {step.error}
              </div>
            ) : hasResults ? (
              <ResultsTable columns={step.columns} rows={step.rows} />
            ) : (
              <p className="text-gray-400">Query returned 0 rows.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
