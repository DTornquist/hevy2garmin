import { getDb } from "@/lib/db";

// Queries the live hevy2garmin Postgres per request — never at build time.
export const dynamic = "force-dynamic";

interface WorkoutItem {
  hevy_id: string;
  title: string;
  when: string | null;
  // Normalised state for the pill: terminal statuses from synced_workouts
  // (success/manual/skipped) or a pending phase from pending_uploads.
  state: string;
  detail: string | null;
  garmin_activity_id: string | null;
  kind: "terminal" | "pending";
}

interface WorkoutsData {
  dbConfigured: boolean;
  items: WorkoutItem[];
}

const EMPTY: WorkoutsData = { dbConfigured: false, items: [] };

async function loadWorkouts(): Promise<WorkoutsData> {
  let sql: ReturnType<typeof getDb>;
  try {
    sql = getDb();
  } catch {
    return EMPTY;
  }

  const [terminal, pending] = await Promise.all([
    sql`
      SELECT hevy_id, title, synced_at, garmin_activity_id,
             COALESCE(status, 'success') AS status
      FROM synced_workouts
      ORDER BY synced_at DESC
      LIMIT 100
    `.catch(
      () =>
        [] as Array<{
          hevy_id: string;
          title: string | null;
          synced_at: string | null;
          garmin_activity_id: string | null;
          status: string;
        }>,
    ),
    sql`
      SELECT hevy_id, phase, next_step, last_error, garmin_activity_id,
             created_at,
             (payload ->> 'title') AS payload_title
      FROM pending_uploads
      ORDER BY created_at DESC
      LIMIT 100
    `.catch(
      () =>
        [] as Array<{
          hevy_id: string;
          phase: string | null;
          next_step: string | null;
          last_error: string | null;
          garmin_activity_id: string | null;
          created_at: string | null;
          payload_title: string | null;
        }>,
    ),
  ]);

  const pendingItems: WorkoutItem[] = pending.map((p) => ({
    hevy_id: p.hevy_id,
    title: p.payload_title ?? "",
    when: p.created_at ?? null,
    state: p.phase ?? "pending",
    detail: p.last_error ?? p.next_step ?? null,
    garmin_activity_id: p.garmin_activity_id ?? null,
    kind: "pending",
  }));

  const pendingIds = new Set(pendingItems.map((p) => p.hevy_id));

  const terminalItems: WorkoutItem[] = terminal
    // A hevy_id in pending_uploads is mid-flight; prefer its pending row.
    .filter((t) => !pendingIds.has(t.hevy_id))
    .map((t) => ({
      hevy_id: t.hevy_id,
      title: t.title ?? "",
      when: t.synced_at ?? null,
      state: t.status,
      detail: null,
      garmin_activity_id: t.garmin_activity_id ?? null,
      kind: "terminal",
    }));

  // Pending first (they need attention), then terminal, each newest-first.
  return { dbConfigured: true, items: [...pendingItems, ...terminalItems] };
}

function fmtDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StatusPill({ item }: { item: WorkoutItem }) {
  // Terminal statuses map to fixed colours; any pending phase is "warm/in-flight".
  const terminalStyles: Record<string, { cls: string; label: string }> = {
    success: { cls: "bg-success/15 text-success", label: "Uploaded" },
    manual: { cls: "bg-warm/15 text-warm", label: "Marked as synced" },
    skipped: { cls: "bg-surface-active text-text-muted", label: "Skipped" },
    failed: { cls: "bg-danger/15 text-danger", label: "Failed" },
  };

  if (item.kind === "terminal") {
    const s = terminalStyles[item.state] ?? {
      cls: "bg-surface-active text-text-secondary",
      label: item.state,
    };
    return (
      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${s.cls}`}>
        {s.label}
      </span>
    );
  }

  // Pending — teal to distinguish from terminal states.
  return (
    <span className="inline-block rounded-full bg-teal/15 px-2.5 py-0.5 text-xs font-medium text-teal">
      {item.state}
    </span>
  );
}

export default async function WorkoutsPage() {
  const data = await loadWorkouts();

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 md:px-6">
      <header className="mb-4">
        <h1 className="text-2xl font-bold text-text">Workouts</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Terminal and in-flight workouts recorded in the database.
        </p>
      </header>

      <div className="mb-6 rounded-lg border border-border bg-surface p-4 text-sm text-text-muted">
        Live Hevy fetch and per-workout sync actions come in a later phase. This
        view is read-only and shows only what the database already knows.
      </div>

      {!data.dbConfigured && (
        <div className="mb-6 rounded-lg border border-warm/40 bg-warm/10 p-4 text-sm text-warm">
          No database is configured (DATABASE_URL is unset). Showing empty state.
        </div>
      )}

      {data.items.length === 0 ? (
        <div className="rounded-lg border border-border bg-surface p-8 text-center">
          <p className="text-sm font-medium text-text-secondary">
            No workouts recorded yet.
          </p>
          <p className="mt-1 text-xs text-text-muted">
            Synced and pending workouts will appear here.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface-elevated">
          {data.items.map((w) => (
            <li
              key={w.hevy_id}
              className="flex items-center justify-between gap-3 px-4 py-3"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-text">
                  {w.title || "Untitled workout"}
                </div>
                <div className="mt-0.5 text-xs text-text-muted">
                  {fmtDate(w.when)}
                  {w.garmin_activity_id && (
                    <span> · Garmin {w.garmin_activity_id}</span>
                  )}
                  {w.detail && (
                    <span className="text-text-secondary"> · {w.detail}</span>
                  )}
                </div>
              </div>
              <StatusPill item={w} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
