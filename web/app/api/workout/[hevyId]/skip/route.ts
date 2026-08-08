import { NextResponse } from "next/server";
import { resolveTerminal } from "@/lib/pending-store";

// Writes the app's own synced_workouts ledger at request time — never at build.
export const dynamic = "force-dynamic";

/**
 * POST /api/workout/[hevyId]/skip
 * Body: { reason?: string }
 *
 * Records a deliberate skip: inserts a terminal 'skipped' row into
 * synced_workouts (so this workout is excluded from future sync candidates) and
 * clears any pending row. DB-only — no Garmin call, no upload.
 *
 * NOTE: auth-gating (session cookie / middleware) is added in the login phase;
 * this route is intentionally unauthenticated for now.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ hevyId: string }> },
) {
  const { hevyId } = await params;
  if (!hevyId) {
    return NextResponse.json({ error: "hevyId is required." }, { status: 400 });
  }

  let body: { reason?: unknown } = {};
  try {
    const text = await request.text();
    if (text) body = JSON.parse(text);
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const reason = typeof body.reason === "string" && body.reason.trim() ? body.reason.trim() : null;

  try {
    await resolveTerminal(hevyId, { status: "skipped", reason, source: "web" });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error }, { status: 500 });
  }

  return NextResponse.json({ ok: true, hevyId, status: "skipped" });
}
