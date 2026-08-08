import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

// Reads the live hevy2garmin Postgres at request time — never at build.
export const dynamic = "force-dynamic";

/**
 * hevy2garmin sync status, read directly from the hevy2garmin Postgres schema
 * (synced_workouts / platform_credentials — see src/hevy2garmin/db_postgres.py).
 *
 * Shape matches `HevyStatus` in hevy2garmin/universal/src/lib/api.ts so the
 * existing Expo app can consume this route too.
 */

interface RecentWorkout {
  hevy_id: string;
  title: string;
  synced_at: string | null;
  calories: number;
  status: string;
}

interface StatusResponse {
  hevyConnected: boolean;
  garminConnected: boolean;
  totalSynced: number;
  syncedThisWeek: number;
  recent: RecentWorkout[];
}

const EMPTY: StatusResponse = {
  hevyConnected: false,
  garminConnected: false,
  totalSynced: 0,
  syncedThisWeek: 0,
  recent: [],
};

export async function GET() {
  let sql: ReturnType<typeof getDb>;
  try {
    sql = getDb();
  } catch {
    // No DATABASE_URL configured — return sane defaults rather than a 500.
    return NextResponse.json(EMPTY);
  }

  // Connection status from platform_credentials. `.catch` guards a missing table
  // (fresh deploy that hasn't run the Python schema bootstrap yet).
  const connected = await sql`
    SELECT platform, status
    FROM platform_credentials
    WHERE platform IN ('hevy', 'garmin')
  `.catch(() => [] as Array<{ platform: string; status: string }>);

  const hevyConnected = connected.some(
    (r) => r.platform === "hevy" && r.status === "connected",
  );
  const garminConnected = connected.some(
    (r) => r.platform === "garmin" && r.status === "connected",
  );

  // Aggregate counts over synced_workouts (success terminal state only).
  const counts = await sql`
    SELECT
      count(*) FILTER (WHERE COALESCE(status, 'success') = 'success')::int AS total,
      count(*) FILTER (
        WHERE COALESCE(status, 'success') = 'success'
          AND synced_at >= (now() - interval '7 days')
      )::int AS week
    FROM synced_workouts
  `.catch(() => [] as Array<{ total: number; week: number }>);

  const totalSynced = counts[0]?.total ?? 0;
  const syncedThisWeek = counts[0]?.week ?? 0;

  const recentRows = await sql`
    SELECT hevy_id, title, synced_at, calories, COALESCE(status, 'success') AS status
    FROM synced_workouts
    ORDER BY synced_at DESC
    LIMIT 8
  `.catch(
    () =>
      [] as Array<{
        hevy_id: string;
        title: string | null;
        synced_at: string | null;
        calories: number | null;
        status: string;
      }>,
  );

  const recent: RecentWorkout[] = recentRows.map((r) => ({
    hevy_id: r.hevy_id,
    title: r.title ?? "",
    synced_at: r.synced_at ?? null,
    calories: Number(r.calories) || 0,
    status: r.status,
  }));

  const body: StatusResponse = {
    // If we have synced rows, Hevy has been talking to us even absent an explicit
    // platform_credentials row.
    hevyConnected: hevyConnected || totalSynced > 0,
    // Any row with a garmin_activity_id proves the Garmin link worked.
    garminConnected,
    totalSynced,
    syncedThisWeek,
    recent,
  };

  return NextResponse.json(body);
}
