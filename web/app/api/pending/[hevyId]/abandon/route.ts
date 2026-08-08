import { NextResponse } from "next/server";
import { deletePending } from "@/lib/pending-store";

// Deletes from the app's own pending_uploads table at request time — never at build.
export const dynamic = "force-dynamic";

/**
 * POST /api/pending/[hevyId]/abandon
 *
 * Drops an in-flight pending_uploads row (e.g. a stuck 'preparing' claim), so
 * the workout can be re-evaluated on the next preview/sync. DB-only: it does NOT
 * touch Garmin and does NOT create a terminal synced_workouts row — the workout
 * simply becomes a fresh candidate again.
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

  let deleted: boolean;
  try {
    deleted = await deletePending(hevyId);
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error }, { status: 500 });
  }

  return NextResponse.json({ ok: true, hevyId, deleted });
}
