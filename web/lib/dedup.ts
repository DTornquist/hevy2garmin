/**
 * Pure dedup decision logic — the SAFE half of the sync engine.
 *
 * These functions decide WHICH Hevy workouts still need syncing. They take
 * plain data (a workout list + the sets of already-synced and pending hevy_ids)
 * and return candidates / the next pick. They perform NO IO: no DB, no Hevy, and
 * crucially no Garmin upload. They are the TS analogue of sync.py's per-workout
 * skip logic (`skip_existing and store.is_synced(wid)` + `pending_by_id.get(wid)`).
 *
 * The three-layer never-duplicate concept (from soma's hevy-upload.ts) maps onto
 * hevy2garmin's schema as:
 *   Layer 1 (already resolved): a terminal `synced_workouts` row exists
 *            (status success/manual/skipped) → excluded via `syncedIds`.
 *   Layer 2 (in flight): a `pending_uploads` row exists (an upload was claimed
 *            or is mid-flight) → excluded via `pendingIds`, so we never
 *            double-claim / double-upload the same workout.
 *   Layer 3 (Garmin 409 on duplicate FIT) lives in the UPLOAD half and is out of
 *            scope here; the pure layer only encodes layers 1 and 2.
 *
 * "Skip if synced OR pending" is the single rule these functions enforce.
 */

/** Minimal shape a workout needs for dedup. `id` is the Hevy workout id (PK). */
export interface DedupWorkout {
  id: string;
  title?: string | null;
  start_time?: string | null;
  [key: string]: unknown;
}

/**
 * True when a workout is NOT yet resolved and NOT in flight — i.e. a real sync
 * candidate. Pure predicate; mirrors the skip rule in sync.py's main loop.
 */
export function isUnsynced(
  workout: DedupWorkout,
  syncedIds: ReadonlySet<string>,
  pendingIds: ReadonlySet<string>,
): boolean {
  const id = workout.id;
  if (!id) return false;
  return !syncedIds.has(id) && !pendingIds.has(id);
}

/**
 * Filter a workout list to the ones still needing a sync: excludes anything with
 * a terminal `synced_workouts` row (layer 1) OR an in-flight `pending_uploads`
 * row (layer 2). Input order is preserved. Pure.
 */
export function filterUnsynced(
  workouts: readonly DedupWorkout[],
  syncedIds: ReadonlySet<string>,
  pendingIds: ReadonlySet<string>,
): DedupWorkout[] {
  return workouts.filter((w) => isUnsynced(w, syncedIds, pendingIds));
}

/**
 * Pick the next workout to sync from a list, applying the same skip rule.
 *
 * Ordering follows the Python pipeline: the first unsynced workout in the given
 * list order is the next one to process (`fetch_workouts` yields newest-first;
 * the loop takes them in that order). Returns null when nothing remains. Pure.
 */
export function pickNextUnsynced(
  workouts: readonly DedupWorkout[],
  syncedIds: ReadonlySet<string>,
  pendingIds: ReadonlySet<string>,
): DedupWorkout | null {
  for (const w of workouts) {
    if (isUnsynced(w, syncedIds, pendingIds)) return w;
  }
  return null;
}

/** A full preview of the dedup decision over a workout list. Pure. */
export interface DedupSummary {
  totalHevy: number;
  syncedCount: number;
  pendingCount: number;
  remaining: number;
  candidates: DedupWorkout[];
  nextUnsynced: DedupWorkout | null;
}

/**
 * Compute the full dedup decision in one pass: the candidate list and the next
 * pick, plus tallies. `syncedCount`/`pendingCount` reflect how many of THESE
 * workouts are already resolved / in flight (intersection with the id sets), so
 * the numbers add up against `totalHevy`. Pure — feeds the /preview route.
 */
export function summarizeDedup(
  workouts: readonly DedupWorkout[],
  syncedIds: ReadonlySet<string>,
  pendingIds: ReadonlySet<string>,
): DedupSummary {
  const candidates = filterUnsynced(workouts, syncedIds, pendingIds);
  let syncedCount = 0;
  let pendingCount = 0;
  for (const w of workouts) {
    if (!w.id) continue;
    if (syncedIds.has(w.id)) syncedCount++;
    else if (pendingIds.has(w.id)) pendingCount++;
  }
  return {
    totalHevy: workouts.length,
    syncedCount,
    pendingCount,
    remaining: candidates.length,
    candidates,
    nextUnsynced: candidates[0] ?? null,
  };
}
