import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

// Writes to the live hevy2garmin Postgres at request time — never at build.
export const dynamic = "force-dynamic";

/**
 * POST /api/mapping/delete
 * Body: { hevy_name: string }
 *
 * Deletes a single custom mapping row by its primary key. Mirrors
 * PostgresDatabase.delete_custom_mapping (db_postgres.py). Only touches
 * `custom_mappings` — no sync/upload side effects.
 */

interface Body {
  hevy_name?: unknown;
}

export async function POST(request: Request) {
  let body: Body;
  try {
    body = (await request.json()) as Body;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const hevyName =
    typeof body.hevy_name === "string" ? body.hevy_name.trim() : "";
  if (!hevyName) {
    return NextResponse.json(
      { error: "hevy_name is required." },
      { status: 400 },
    );
  }

  let sql: ReturnType<typeof getDb>;
  try {
    sql = getDb();
  } catch {
    return NextResponse.json(
      { error: "DATABASE_URL not configured." },
      { status: 503 },
    );
  }

  try {
    await sql`DELETE FROM custom_mappings WHERE hevy_name = ${hevyName}`;
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
