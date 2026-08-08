"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        router.push("/dashboard");
        router.refresh();
      } else {
        setError("Incorrect password");
        setLoading(false);
      }
    } catch {
      setError("Something went wrong. Try again.");
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="mb-1 text-2xl font-bold text-text">hevy2garmin</h1>
      <p className="mb-6 text-sm text-text-secondary">Enter your dashboard password.</p>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <input
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="rounded-lg border border-border bg-surface px-4 py-3 text-text outline-none focus:border-teal"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="submit"
          disabled={loading || password.length === 0}
          className="rounded-lg bg-teal px-4 py-3 font-medium text-black transition-opacity disabled:opacity-50"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
