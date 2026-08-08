import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { syncOneWorkout } from "@/lib/sync-one";
import { getDb } from "@/lib/db";
import { verifySession, SESSION_COOKIE, authEnabled } from "@/lib/auth";

// Reads live Hevy + Postgres (and, on the live path, Garmin) at request time.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * POST /api/sync-one  —  DRY-RUN BY DEFAULT.
 *
 * Runs the single-workout Hevy→Garmin upload engine (lib/sync-one). Because a
 * bad upload creates a duplicate Garmin/Strava activity — a hard user
 * constraint — this route is dry-run unless the request EXPLICITLY opts into a
 * live upload AND is authorized.
 *
 * A live upload fires only when BOTH hold:
 *   1. the request asks for it: `?live=1` (or body { live: 1 | true }); AND
 *   2. the request is authorized: a valid h2g session cookie, OR an
 *      `Authorization: Bearer <CRON_SECRET>` header matching env CRON_SECRET.
 *
 * Anything short of both runs a dry-run (never uploads). The response mirrors
 * the Python sync-one shape: { status, dryRun, wouldUpload, dedupDecision,
 * synced/skipped/remaining/deferred/error, ... }.
 */

async function isAuthorized(request: Request): Promise<boolean> {
  // CRON_SECRET via Bearer token (for scheduled/cron invocations).
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret) {
    const auth = request.headers.get("authorization") ?? "";
    const m = auth.match(/^Bearer\s+(.+)$/i);
    if (m && m[1] === cronSecret) return true;
  }
  // Session cookie (a logged-in dashboard user). When auth is disabled (no
  // password / secret configured), the app has no session gate — treat as
  // authorized so a local/self-hosted deploy without a password still works.
  if (!authEnabled()) return true;
  const store = await cookies();
  const cookie = store.get(SESSION_COOKIE)?.value ?? null;
  return verifySession(cookie);
}

function wantsLive(request: Request, body: Record<string, unknown>): boolean {
  const q = new URL(request.url).searchParams.get("live");
  if (q === "1" || q === "true") return true;
  const b = body.live;
  return b === 1 || b === true || b === "1" || b === "true";
}

export async function POST(request: Request) {
  let body: Record<string, unknown> = {};
  try {
    const text = await request.text();
    if (text) body = JSON.parse(text);
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const requestedLive = wantsLive(request, body);
  const authorized = requestedLive ? await isAuthorized(request) : false;

  // Live ONLY when explicitly requested AND authorized. Otherwise dry-run.
  const dryRun = !(requestedLive && authorized);

  if (requestedLive && !authorized) {
    return NextResponse.json(
      { error: "Unauthorized: a live upload requires a session or CRON_SECRET." },
      { status: 401 },
    );
  }

  let sql: ReturnType<typeof getDb>;
  try {
    sql = getDb();
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: `DB unavailable: ${error}` }, { status: 503 });
  }

  try {
    const result = await syncOneWorkout(sql, { dryRun });
    return NextResponse.json(result);
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error }, { status: 500 });
  }
}
