/**
 * Admin-user gating.
 *
 * The site's only admin today is keller.scholl@gmail.com, but everything
 * runs through `isAdmin(email)` so future additions don't sprawl. The
 * email comes from `auth.users.email` which Supabase populates from
 * Google OAuth — so it's verified by Google, not self-attested. Safe
 * to gate sensitive UI on.
 *
 * Used by:
 *   - /me/diagnostics — the admin-only Test Functionality runner
 *   - any future admin surface (rate-limit dashboards, user list, etc.)
 *
 * SECURITY: This is a CLIENT-SIDE gate. It hides admin UI from non-
 * admins but doesn't enforce server-side authorization. The
 * diagnostic runner happens to only call endpoints the user can
 * already hit (their own saved_dashboards, public pages, etc.) so
 * client-side gating is sufficient there. Don't reuse this for any
 * surface that lets an admin do something a regular user can't do at
 * the database layer — for that, write a Supabase RLS policy or a
 * server-side check.
 */

/**
 * The set of admin emails. Add new admins by extending this set.
 *
 * Email matching is exact + case-sensitive. Google OAuth normalizes
 * the email to lowercase for Gmail addresses on the way out, so the
 * stored email in `auth.users.email` is the canonical form to match
 * against.
 */
export const ADMIN_EMAILS: ReadonlySet<string> = new Set([
  "keller.scholl@gmail.com",
]);

/**
 * Whether the given email is an admin. Tolerates `null` / `undefined`
 * so callers can pass a session.user?.email straight through without
 * defensive ?? "" tricks.
 */
export function isAdmin(email: string | null | undefined): boolean {
  if (!email) return false;
  return ADMIN_EMAILS.has(email);
}
