import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

// Writes to the live hevy2garmin Postgres at request time — never at build.
export const dynamic = "force-dynamic";

/**
 * POST /api/mapping
 * Body: { hevy_name: string, category: number, subcategory?: number }
 *
 * Upserts a single row into `custom_mappings` (hevy_name PK). This is the only
 * table this web app is allowed to write to — no sync/upload side effects. The
 * upsert mirrors PostgresDatabase.save_custom_mapping (db_postgres.py).
 */

interface Body {
  hevy_name?: unknown;
  category?: unknown;
  subcategory?: unknown;
}

function toInt(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (typeof value === "string" && /^-?\d+$/.test(value.trim())) {
    return Number.parseInt(value.trim(), 10);
  }
  return null;
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

  const category = toInt(body.category);
  if (category === null) {
    return NextResponse.json(
      { error: "category must be an integer." },
      { status: 400 },
    );
  }

  // subcategory is optional and defaults to 0 (matches the DB column default).
  const subcategory = body.subcategory === undefined ? 0 : toInt(body.subcategory);
  if (subcategory === null) {
    return NextResponse.json(
      { error: "subcategory must be an integer." },
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
    await sql`
      INSERT INTO custom_mappings (hevy_name, category, subcategory)
      VALUES (${hevyName}, ${category}, ${subcategory})
      ON CONFLICT (hevy_name) DO UPDATE SET
        category = EXCLUDED.category,
        subcategory = EXCLUDED.subcategory
    `;
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error }, { status: 500 });
  }

  return NextResponse.json({ ok: true });
}
