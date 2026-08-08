/** Throws in production if any required env var is missing or too short. */
export function assertProdEnv(): void {
  if (process.env.NODE_ENV !== "production") return;

  const missing: string[] = [];
  if (!process.env.DATABASE_URL) missing.push("DATABASE_URL");
  // Either a shared login password or an explicit signing secret must be set.
  const hasPassword = Boolean(process.env.H2G_PASSWORD && process.env.H2G_PASSWORD.length >= 8);
  const hasSecret = Boolean(process.env.HEVY2GARMIN_SECRET && process.env.HEVY2GARMIN_SECRET.length >= 32);
  if (!hasPassword && !hasSecret) {
    missing.push("H2G_PASSWORD (min 8 chars) or HEVY2GARMIN_SECRET (min 32 chars)");
  }
  if (missing.length > 0) {
    throw new Error(`Missing required env vars: ${missing.join(", ")}`);
  }
}
