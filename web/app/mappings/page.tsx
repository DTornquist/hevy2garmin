import { HEVY_TO_GARMIN } from "hevy2garmin";
import { getDb } from "@/lib/db";
import {
  CATEGORY_OPTIONS,
  categoryName,
} from "@/lib/garmin-categories";
import { DeleteMappingButton, MappingForm } from "@/components/mapping-form";

// Queries the live hevy2garmin Postgres per request — never at build time.
export const dynamic = "force-dynamic";

interface CustomMapping {
  hevy_name: string;
  category: number;
  subcategory: number;
}

interface MappingsData {
  dbConfigured: boolean;
  custom: CustomMapping[];
  builtinCount: number;
  builtinSample: Array<{ name: string; category: number; subcategory: number }>;
}

async function loadMappings(): Promise<MappingsData> {
  // The built-in map ships with the package — available regardless of DB state.
  const builtinEntries = Object.entries(HEVY_TO_GARMIN);
  const builtinSample = builtinEntries.slice(0, 12).map(([name, pair]) => ({
    name,
    category: pair[0],
    subcategory: pair[1],
  }));

  let sql: ReturnType<typeof getDb>;
  try {
    sql = getDb();
  } catch {
    return {
      dbConfigured: false,
      custom: [],
      builtinCount: builtinEntries.length,
      builtinSample,
    };
  }

  const rows = await sql`
    SELECT hevy_name, category, subcategory
    FROM custom_mappings
    ORDER BY hevy_name ASC
  `.catch(() => [] as CustomMapping[]);

  return {
    dbConfigured: true,
    custom: rows.map((r) => ({
      hevy_name: r.hevy_name,
      category: Number(r.category),
      subcategory: Number(r.subcategory),
    })),
    builtinCount: builtinEntries.length,
    builtinSample,
  };
}

export default async function MappingsPage() {
  const data = await loadMappings();

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 md:px-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold text-text">Exercise mappings</h1>
        <p className="mt-1 text-sm text-text-secondary">
          How Hevy exercises map to Garmin FIT exercise categories.
        </p>
      </header>

      {!data.dbConfigured && (
        <div className="mb-6 rounded-lg border border-warm/40 bg-warm/10 p-4 text-sm text-warm">
          No database is configured (DATABASE_URL is unset). Custom mappings are
          unavailable; the built-in map below still works.
        </div>
      )}

      {/* Add a custom mapping */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-text">
          Add a custom mapping
        </h2>
        <div className="rounded-xl border border-border bg-surface-elevated p-4">
          <MappingForm categories={CATEGORY_OPTIONS} />
          <p className="mt-3 text-xs text-text-muted">
            A custom mapping overrides the built-in map for that exact Hevy
            exercise name. Sub ID 0 uses the category&apos;s generic exercise.
          </p>
        </div>
      </section>

      {/* Custom mappings */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-text">
          Your custom mappings ({data.custom.length})
        </h2>
        {data.custom.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface p-6 text-center text-sm text-text-muted">
            No custom mappings yet. Add one above to override a built-in mapping.
          </div>
        ) : (
          <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface-elevated">
            {data.custom.map((m) => (
              <li
                key={m.hevy_name}
                className="flex items-center justify-between gap-3 px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-text">
                    {m.hevy_name}
                  </div>
                  <div className="mt-0.5 text-xs text-text-muted">
                    {categoryName(m.category)} · cat {m.category} · sub{" "}
                    {m.subcategory}
                  </div>
                </div>
                <DeleteMappingButton hevyName={m.hevy_name} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Built-in map */}
      <section>
        <h2 className="mb-1 text-lg font-semibold text-text">
          Built-in map
        </h2>
        <p className="mb-3 text-sm text-text-secondary">
          {data.builtinCount} exercises are mapped out of the box. Sample:
        </p>
        <div className="overflow-x-auto rounded-xl border border-border bg-surface-elevated">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-muted">
                <th className="px-4 py-2 font-medium">Hevy exercise</th>
                <th className="px-4 py-2 font-medium">Garmin category</th>
                <th className="px-4 py-2 text-right font-medium">Cat</th>
                <th className="px-4 py-2 text-right font-medium">Sub</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.builtinSample.map((b) => (
                <tr key={b.name}>
                  <td className="px-4 py-2 font-medium text-text">{b.name}</td>
                  <td className="px-4 py-2 text-text-secondary">
                    {categoryName(b.category)}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-text-muted">
                    {b.category}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-text-muted">
                    {b.subcategory}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
