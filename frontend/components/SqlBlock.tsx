"use client";

import { useState } from "react";

interface SqlBlockProps {
  sql: string;
  onRun: (sql: string) => void;
  running: boolean;
}

export default function SqlBlock({ sql, onRun, running }: SqlBlockProps) {
  const [confirmed, setConfirmed] = useState(false);

  const isDestructive = /\b(DROP|DELETE|TRUNCATE|ALTER)\b/i.test(sql);

  function handleRunClick() {
    if (isDestructive && !confirmed) {
      setConfirmed(true);
      return;
    }
    onRun(sql);
    setConfirmed(false);
  }

  return (
    <div className="mt-2 overflow-hidden rounded-md border border-gray-700 bg-gray-900">
      <div className="flex items-center justify-between px-4 py-2">
        <span className="text-xs font-medium text-gray-400">SQL</span>
        {confirmed ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-yellow-400">
              This query is destructive. Are you sure?
            </span>
            <button
              onClick={() => { onRun(sql); setConfirmed(false); }}
              className="rounded bg-red-600 px-2 py-1 text-xs text-white hover:bg-red-700"
            >
              Yes, Run
            </button>
            <button
              onClick={() => setConfirmed(false)}
              className="rounded border border-gray-600 px-2 py-1 text-xs text-gray-300 hover:bg-gray-700"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            onClick={handleRunClick}
            disabled={running}
            className="rounded bg-gray-700 px-2 py-1 text-xs text-gray-200 hover:bg-gray-600 disabled:opacity-50"
          >
            {running ? "Running…" : "Run Query"}
          </button>
        )}
      </div>
      <pre className="overflow-x-auto px-4 pb-4 text-sm text-green-300">
        <code>{sql.trim()}</code>
      </pre>
    </div>
  );
}
