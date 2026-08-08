import postgres from "postgres";

/**
 * Tagged-template SQL function matching the @neondatabase/serverless shape
 * the ecosystem web apps are written against: `sql` returns Promise<rows[]>.
 *
 * Exposes `.json(x)` as a passthrough helper to mark values that must be sent
 * as a JSONB payload. Do NOT JSON.stringify values before `sql.json(x)` — that
 * produces a double-encoded string in the column.
 *
 * Reads the hevy2garmin Postgres URL from DATABASE_URL (same var the Python
 * PostgresDatabase reads).
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = any;

type SqlTag = {
  (strings: TemplateStringsArray, ...values: unknown[]): Promise<Row[]>;
  json: <T>(value: T) => unknown;
};

let cached: SqlTag | null = null;

export function getDb(): SqlTag {
  if (cached) return cached;
  const url = process.env.DATABASE_URL;
  if (!url) {
    throw new Error("DATABASE_URL not set");
  }
  const client = postgres(url, { prepare: false });

  const tag = ((strings: TemplateStringsArray, ...values: unknown[]) =>
    (client as unknown as (s: TemplateStringsArray, ...v: unknown[]) => Promise<unknown[]>)(strings, ...values)
      .then((rows) => Array.from(rows) as Row[])) as SqlTag;

  tag.json = <T,>(value: T) => (client as unknown as { json: (v: T) => unknown }).json(value);

  cached = tag;
  return cached;
}
