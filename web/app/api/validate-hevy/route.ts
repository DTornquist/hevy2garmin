import { NextResponse } from "next/server";
import { HevyClient } from "hevy2garmin";

// Calls the live Hevy API only when invoked at runtime — never at build.
export const dynamic = "force-dynamic";

/**
 * GET /api/validate-hevy?key=<hevy-api-key>
 *
 * Tests a Hevy API key by asking the Hevy API for the caller's workout count.
 * A valid key returns `{ valid: true, workout_count }`; anything else returns
 * `{ valid: false, error }`. This never touches the database and never fires an
 * upload — it is a read-only probe of the supplied key.
 */
export async function GET(request: Request) {
  const key = new URL(request.url).searchParams.get("key")?.trim();
  if (!key) {
    return NextResponse.json(
      { valid: false, error: "Missing ?key= query parameter." },
      { status: 400 },
    );
  }

  try {
    const client = new HevyClient(key);
    const workout_count = await client.getWorkoutCount();
    return NextResponse.json({ valid: true, workout_count });
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ valid: false, error });
  }
}
