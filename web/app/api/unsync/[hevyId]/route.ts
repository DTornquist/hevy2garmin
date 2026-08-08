import { NextResponse } from "next/server";
import { unsync } from "@/lib/pending-store";

// Deletes from the app's own synced_workouts table at request time — never at build.
export const dynamic = "force-dynamic";

/**
 * POST /api/unsync/[hevyId]
 *
 * Removes a workout's terminal synced_workouts row so it becomes a sync
 * candidate again. DB-ONLY: this deliberately does NOT delete the corresponding
 * Garmin activity — deleting a Garmin activity is a destructive Garmin write and
 * is out of scope for the safe half of the engine. Only the local ledger row is
 * removed here.
 *
 * NOTE: auth-gating (session cookie / middleware) is added in the login phase;
 * this route is intentionally unauthenticated for now.
 */
export async function POST(
  _request: Request,
  { params }: { params: Promise<{ hevyId: string }> },
) {
  const { hevyId } = await params;
  if (!hevyId) {
    return NextResponse.json({ error: "hevyId is required." }, { status: 400 });
  }

  let removed: boolean;
  try {
    removed = await unsync(hevyId);
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error }, { status: 500 });
  }

  return NextResponse.json({ ok: true, hevyId, removed });
}
