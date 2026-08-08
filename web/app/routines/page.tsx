// Static placeholder — routine sync is a later phase.
export const dynamic = "force-static";

export default function RoutinesPage() {
  return (
    <main className="mx-auto max-w-5xl px-4 py-8 md:px-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-text">Routines</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Hevy routine → Garmin planned-workout sync.
        </p>
      </header>

      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <p className="text-sm font-medium text-text-secondary">
          Coming in a later phase.
        </p>
        <p className="mt-1 text-xs text-text-muted">
          Routine syncing isn&apos;t part of the read-only web app yet.
        </p>
      </div>
    </main>
  );
}
