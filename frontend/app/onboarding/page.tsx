"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

export default function OnboardingPage() {
  const router = useRouter();
  const [connectionString, setConnectionString] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function guardAuth() {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        router.replace("/login");
      }
    }
    guardAuth();
  }, [router]);

  async function handleConnect() {
    setError("");
    setLoading(true);

    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) {
      router.replace("/login");
      return;
    }

    try {
      const res = await fetch(`${API_URL}/onboarding/connect`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ connection_string: connectionString }),
      });

      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Connection failed.");
        setLoading(false);
        return;
      }

      router.replace("/chat");
    } catch {
      setError("Network error. Is the backend running?");
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="mb-2 text-2xl font-semibold text-gray-800">
          Connect your database
        </h1>
        <p className="mb-6 text-sm text-gray-500">
          Paste your database connection string below.
        </p>

        {error && (
          <div className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="mb-2">
          <input
            type="text"
            value={connectionString}
            onChange={(e) => setConnectionString(e.target.value)}
            disabled={loading}
            className="w-full rounded border border-gray-300 px-3 py-2 font-mono text-sm text-gray-800 focus:border-blue-500 focus:outline-none disabled:bg-gray-50"
            placeholder="postgresql://user:password@host:5432/dbname"
          />
        </div>

        <p className="mb-6 text-xs text-gray-400">
          Supported: PostgreSQL, MySQL, SQLite
        </p>

        <button
          onClick={handleConnect}
          disabled={loading || !connectionString.trim()}
          className="w-full rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Reading your schema…
            </span>
          ) : (
            "Connect"
          )}
        </button>
      </div>
    </div>
  );
}
