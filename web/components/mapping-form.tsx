"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

interface CategoryOption {
  id: number;
  name: string;
}

/**
 * Inline add/edit form for a custom exercise mapping. Posts to /api/mapping and
 * refreshes the server-rendered mappings list on success. The category dropdown
 * is seeded from the server (which reads /api/garmin-categories' source map), so
 * this component does no fetching of its own.
 */
export function MappingForm({ categories }: { categories: CategoryOption[] }) {
  const router = useRouter();
  const [hevyName, setHevyName] = useState("");
  const [category, setCategory] = useState(categories[0]?.id ?? 0);
  const [subcategory, setSubcategory] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const name = hevyName.trim();
    if (!name) {
      setError("Enter the exact Hevy exercise name.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch("/api/mapping", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hevy_name: name,
          category,
          subcategory: Number.parseInt(subcategory || "0", 10),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
      };
      if (!res.ok || !data.ok) {
        setError(data.error ?? `Request failed (${res.status}).`);
        return;
      }
      setHevyName("");
      setSubcategory("0");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
      <div className="flex-1">
        <label className="mb-1 block text-xs text-text-muted" htmlFor="mf-name">
          Hevy exercise name (exact)
        </label>
        <input
          id="mf-name"
          type="text"
          value={hevyName}
          onChange={(e) => setHevyName(e.target.value)}
          placeholder="e.g. Cable Lateral Raise"
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-muted focus:border-teal focus:outline-none"
        />
      </div>
      <div>
        <label className="mb-1 block text-xs text-text-muted" htmlFor="mf-cat">
          Garmin category
        </label>
        <select
          id="mf-cat"
          value={category}
          onChange={(e) => setCategory(Number.parseInt(e.target.value, 10))}
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text focus:border-teal focus:outline-none sm:w-48"
        >
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} ({c.id})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-xs text-text-muted" htmlFor="mf-sub">
          Sub ID
        </label>
        <input
          id="mf-sub"
          type="number"
          min={0}
          value={subcategory}
          onChange={(e) => setSubcategory(e.target.value)}
          className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text focus:border-teal focus:outline-none sm:w-20"
        />
      </div>
      <button
        type="submit"
        disabled={busy}
        className="rounded-lg bg-teal/20 px-4 py-2 text-sm font-medium text-teal transition-colors hover:bg-teal/30 disabled:opacity-50"
      >
        {busy ? "Saving…" : "Save"}
      </button>
      {error && (
        <p className="text-xs text-danger sm:self-center" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

/**
 * Delete button for a single custom mapping. Posts to /api/mapping/delete and
 * refreshes the list.
 */
export function DeleteMappingButton({ hevyName }: { hevyName: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (!confirm(`Delete custom mapping for "${hevyName}"?`)) return;
    setBusy(true);
    try {
      await fetch("/api/mapping/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hevy_name: hevyName }),
      });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={remove}
      disabled={busy}
      className="rounded-lg border border-danger/30 px-3 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10 disabled:opacity-50"
    >
      {busy ? "…" : "Delete"}
    </button>
  );
}
