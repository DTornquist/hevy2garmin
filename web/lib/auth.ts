/**
 * Shared-password session auth for the hevy2garmin web app.
 *
 * Wire-compatible with the existing Python FastAPI dashboard
 * (src/hevy2garmin/auth.py): cookie value is `v1.<ts>.<sig>`, the signature is
 * the HMAC-SHA256 of `v1.<ts>` under a key, rendered as hex and TRUNCATED to the
 * first 32 hex chars, and sessions expire after 30 days.
 *
 * Key derivation (matches the Python behaviour so a cookie minted by either
 * implementation verifies against the other):
 *   - If HEVY2GARMIN_SECRET is set, the raw secret bytes are the HMAC key.
 *   - Otherwise the key is SHA-256("h2g-session-" + H2G_PASSWORD) — the exact
 *     derivation used by auth.py, so existing password-only deployments keep
 *     working with no cookie rotation.
 *
 * `check_password` compares the login candidate against H2G_PASSWORD.
 */

const SESSION_TTL_SECONDS = 30 * 24 * 60 * 60;
const CLOCK_SKEW_SECONDS = 300;

export const SESSION_COOKIE = "h2g_session";

function toHex(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let out = "";
  for (const b of bytes) out += b.toString(16).padStart(2, "0");
  return out;
}

let cachedKey: { material: string; key: CryptoKey } | null = null;

/**
 * Resolve the HMAC signing key. Prefers HEVY2GARMIN_SECRET; falls back to the
 * password-derived key so it stays wire-compatible with the Python dashboard.
 */
async function getKey(): Promise<CryptoKey> {
  const secret = process.env.HEVY2GARMIN_SECRET;
  const password = process.env.H2G_PASSWORD;

  let material: string;
  let rawKey: Uint8Array;

  if (secret) {
    material = `secret:${secret}`;
    rawKey = new TextEncoder().encode(secret);
  } else {
    if (!password) throw new Error("H2G_PASSWORD not set (and no HEVY2GARMIN_SECRET)");
    material = `password:${password}`;
    // SHA-256("h2g-session-" + password) — matches auth.py `_secret()`.
    const digest = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(`h2g-session-${password}`),
    );
    rawKey = new Uint8Array(digest);
  }

  if (cachedKey && cachedKey.material === material) return cachedKey.key;

  const key = await crypto.subtle.importKey(
    "raw",
    rawKey as unknown as ArrayBuffer,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
  cachedKey = { material, key };
  return key;
}

/** HMAC-SHA256 of `data`, hex-encoded and truncated to 32 chars (matches auth.py). */
async function hmacHex32(data: string): Promise<string> {
  const key = await getKey();
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return toHex(sig).slice(0, 32);
}

/** True when auth is configured (either a secret or a password is present). */
export function authEnabled(): boolean {
  return Boolean(process.env.HEVY2GARMIN_SECRET || process.env.H2G_PASSWORD);
}

/** Create a signed session cookie value: `v1.<ts>.<sig>`. */
export async function signSession(issuedAt?: number): Promise<string> {
  const ts = issuedAt ?? Math.floor(Date.now() / 1000);
  const payload = `v1.${ts}`;
  const sig = await hmacHex32(payload);
  return `${payload}.${sig}`;
}

/** Verify a session cookie is well-formed, unexpired, and correctly signed. */
export async function verifySession(cookie: string | null): Promise<boolean> {
  if (!cookie) return false;
  const m = cookie.match(/^v1\.(\d+)\.([0-9a-f]{32})$/);
  if (!m) return false;
  const ts = Number(m[1]);
  const sig = m[2];
  const now = Math.floor(Date.now() / 1000);
  if (now - ts > SESSION_TTL_SECONDS) return false;
  if (ts > now + CLOCK_SKEW_SECONDS) return false;
  try {
    const expected = await hmacHex32(`v1.${ts}`);
    if (sig.length !== expected.length) return false;
    // Constant-time compare.
    let diff = 0;
    for (let i = 0; i < sig.length; i++) diff |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
    return diff === 0;
  } catch {
    return false;
  }
}

/** Constant-time comparison of a login candidate against H2G_PASSWORD. */
export function checkPassword(candidate: string): boolean {
  const pw = process.env.H2G_PASSWORD;
  if (!pw) return false;
  if (candidate.length !== pw.length) return false;
  let diff = 0;
  for (let i = 0; i < pw.length; i++) diff |= candidate.charCodeAt(i) ^ pw.charCodeAt(i);
  return diff === 0;
}
