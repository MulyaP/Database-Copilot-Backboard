"use client";

import QueryStepBlock from "./QueryStepBlock";
import type { Message } from "@/app/chat/page";

interface MessageBubbleProps {
  message: Message;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  // ── User message ─────────────────────────────────────────────────────
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-3 text-sm text-white shadow-lg">
          {message.content}
        </div>
      </div>
    );
  }

  // ── Assistant message ─────────────────────────────────────────────────
  const hasSteps = message.steps && message.steps.length > 0;

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-3">

        {/* Agentic query steps (collapsed by default, click to expand) */}
        {hasSteps && (
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-gray-400">
              {message.steps!.length} quer{message.steps!.length === 1 ? "y" : "ies"} run automatically
            </p>
            {message.steps!.map((step, i) => (
              <QueryStepBlock key={i} step={step} index={i} />
            ))}
          </div>
        )}

        {/* Final answer */}
        <div className="rounded-2xl border border-gray-700 bg-gray-800 px-5 py-4 text-sm text-gray-200 shadow-lg">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>

      </div>
    </div>
  );
}
