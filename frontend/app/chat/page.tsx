"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import ChatWindow from "@/components/ChatWindow";
import ApprovalCard from "@/components/ApprovalCard";
import QueryStepBlock from "@/components/QueryStepBlock";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

// ── Shared types (also imported by components) ────────────────────────────────
export interface QueryStep {
  sql: string;
  columns: string[];
  rows: unknown[][];
  error?: string;
  kind?: "auto" | "approved" | "rejected" | "blocked";
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  steps?: QueryStep[];
}

/**
 * Tracks the state of a response that hasn't finished yet.
 * The loop may run through several SELECTs automatically, then pause
 * at a write query and wait for the user's decision before resuming.
 */
interface InProgress {
  /** Steps completed so far in the current response (auto-SELECTs, etc.) */
  accumulatedSteps: QueryStep[];
  /** Set when the loop is paused waiting for user approval. */
  pendingApproval: { sql: string } | null;
  /** True while a /chat/execute request is in flight. */
  deciding: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function getAuthHeader(): Promise<string | null> {
  const { data: { session } } = await supabase.auth.getSession();
  return session ? `Bearer ${session.access_token}` : null;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "I've read your schema. Ask me anything about your database." },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [inProgress, setInProgress] = useState<InProgress | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Derived: true when the UI is busy (waiting for LLM or for execute round-trip)
  const busy = sending || (inProgress?.deciding ?? false);
  // Derived: true when input should be blocked (either busy or waiting for user approval)
  const inputBlocked = busy || inProgress?.pendingApproval != null;

  useEffect(() => {
    async function guardAuth() {
      const { data: { session } } = await supabase.auth.getSession();
      if (!session) { router.replace("/login"); return; }
      const { data } = await supabase
        .from("connections").select("id").eq("user_id", session.user.id).single();
      if (!data) router.replace("/onboarding");
    }
    guardAuth();
  }, [router]);

  // ── handleSend: start a new agentic round ──────────────────────────────────
  async function handleSend() {
    const text = input.trim();
    if (!text || inputBlocked) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setSending(true);
    setInProgress({ accumulatedSteps: [], pendingApproval: null, deciding: false });

    const auth = await getAuthHeader();
    if (!auth) { router.replace("/login"); return; }

    try {
      const res = await fetch(`${API_URL}/chat/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: auth },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();

      if (!res.ok) {
        finaliseWithError(data.detail || "Something went wrong.");
        return;
      }

      handleLoopResponse(data, []);
    } catch {
      finaliseWithError("Network error. Is the backend running?");
    } finally {
      setSending(false);
    }
  }

  // ── handleDecision: user approved or rejected a write query ───────────────
  async function handleDecision(approved: boolean) {
    if (!inProgress?.pendingApproval) return;

    const sql = inProgress.pendingApproval.sql;
    setInProgress((prev) => prev ? { ...prev, deciding: true } : prev);

    const auth = await getAuthHeader();
    if (!auth) { router.replace("/login"); return; }

    try {
      const res = await fetch(`${API_URL}/chat/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: auth },
        body: JSON.stringify({ sql, approved }),
      });
      const data = await res.json();

      if (!res.ok) {
        finaliseWithError(data.detail || "Execution failed.");
        return;
      }

      handleLoopResponse(data, inProgress.accumulatedSteps);
    } catch {
      finaliseWithError("Network error during query execution.");
    }
  }

  /**
   * Process a ChatMessageResponse from either /chat/message or /chat/execute.
   * - "done"            → finalise the assistant message
   * - "needs_approval"  → update inProgress with the pending SQL
   *
   * @param data            The parsed JSON response body
   * @param previousSteps   Steps accumulated from earlier rounds
   */
  function handleLoopResponse(data: {
    status: string;
    reply?: string;
    completed_steps?: QueryStep[];
    pending_sql?: string;
  }, previousSteps: QueryStep[]) {
    const newSteps = data.completed_steps ?? [];
    const allSteps = [...previousSteps, ...newSteps];

    if (data.status === "done") {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply ?? "", steps: allSteps },
      ]);
      setInProgress(null);
    } else if (data.status === "needs_approval") {
      setInProgress({
        accumulatedSteps: allSteps,
        pendingApproval: { sql: data.pending_sql ?? "" },
        deciding: false,
      });
    }
  }

  function finaliseWithError(message: string) {
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        content: `Error: ${message}`,
        steps: inProgress?.accumulatedSteps ?? [],
      },
    ]);
    setInProgress(null);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <h1 className="text-base font-semibold text-gray-800">Database Copilot</h1>
        <button onClick={handleSignOut} className="text-sm text-gray-500 hover:text-gray-700">
          Sign out
        </button>
      </div>

      {/* Finalised messages */}
      <ChatWindow messages={messages} />

      {/* In-progress block — shown while a response is being built */}
      {inProgress && (
        <div className="mx-auto w-full max-w-3xl space-y-3 px-4 pb-3">

          {/* Auto-run steps completed so far */}
          {inProgress.accumulatedSteps.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-gray-400">
                {inProgress.accumulatedSteps.length} quer{inProgress.accumulatedSteps.length === 1 ? "y" : "ies"} run automatically
              </p>
              {inProgress.accumulatedSteps.map((step, i) => (
                <QueryStepBlock key={i} step={step} index={i} />
              ))}
            </div>
          )}

          {/* Approval card — blocks input until user decides */}
          {inProgress.pendingApproval ? (
            <ApprovalCard
              sql={inProgress.pendingApproval.sql}
              deciding={inProgress.deciding}
              onApprove={() => handleDecision(true)}
              onReject={() => handleDecision(false)}
            />
          ) : (
            /* Thinking indicator — LLM or execute is in flight */
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-300 border-t-blue-500" />
              Thinking…
            </div>
          )}
        </div>
      )}

      {/* Input bar — disabled while waiting for LLM or user approval */}
      <div className="border-t border-gray-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-end gap-3">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={inputBlocked}
            rows={1}
            className="flex-1 resize-none rounded border border-gray-300 px-3 py-2 text-sm text-gray-800 focus:border-blue-500 focus:outline-none disabled:bg-gray-50 disabled:text-gray-400"
            placeholder={
              inProgress?.pendingApproval
                ? "Waiting for your decision above…"
                : "Ask anything about your database… (Enter to send)"
            }
            style={{ maxHeight: "120px", overflowY: "auto" }}
          />
          <button
            onClick={handleSend}
            disabled={inputBlocked || !input.trim()}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {sending && !inProgress?.pendingApproval ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Thinking…
              </span>
            ) : (
              "Send"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
