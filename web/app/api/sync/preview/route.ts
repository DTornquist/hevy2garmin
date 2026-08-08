import { NextResponse } from "next/server";
import { fetchAllWorkouts } from "@/lib/hevy-sync";
import { loadSyncedIds, loadPendingIds } from "@/lib/pending-store";
import { summarizeDedup, type DedupWorkout } from "@/lib/dedup";

// Reads the live Hevy API + hevy2garmin Postgres at request time — never at build.
export const dynamic = "force-dynamic";

/**
 * GET /api/sync/preview  —  DRY RUN ONLY.
 *
 * Computes what a sync WOULD do without doing any of it. It:
 *   1. reads the full Hevy workout list (READ-only Hevy call),
 *   2. loads the synced + pending id sets from the app's own Postgres,
 *   3. runs the pure dedup in lib/dedup to find the remaining candidates.
 *
 * It NEVER generates or uploads a FIT, NEVER calls Garmin, and NEVER writes to
 * any table. It is purely a preview of the safe half of the sync decision.
 */

interface PreviewResponse {
  totalHevy: number;
  syncedCount: number;
  pendingCount: number;
  remaining: number;
  nextUnsynced: { hevy_id: string; title: string | null; start_time: string | null } | null;
  candidates: number;
}

function nextView(w: DedupWorkout | null): PreviewResponse["nextUnsynced"] {
  if (!w) return null;
  return {
    hevy_id: w.id,
    title: (w.title as string | null) ?? null,
    start_time: (w.start_time as string | null) ?? null,
  };
}

export async function GET() {
  let workouts: DedupWorkout[];
  try {
    workouts = (await fetchAllWorkouts()) as DedupWorkout[];
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `Hevy read failed: ${error}` }, { status: 502 });
  }

  let syncedIds: Set<string>;
  let pendingIds: Set<string>;
  try {
    [syncedIds, pendingIds] = await Promise.all([loadSyncedIds(), loadPendingIds()]);
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `DB read failed: ${error}` }, { status: 503 });
  }

  const summary = summarizeDedup(workouts, syncedIds, pendingIds);

  const body: PreviewResponse = {
    totalHevy: summary.totalHevy,
    syncedCount: summary.syncedCount,
    pendingCount: summary.pendingCount,
    remaining: summary.remaining,
    nextUnsynced: nextView(summary.nextUnsynced),
    candidates: summary.candidates.length,
  };
  return NextResponse.json(body);
}
