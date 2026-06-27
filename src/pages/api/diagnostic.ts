/**
 * POST /api/diagnostic — auto-post a diagnostic report as a comment
 * on a fixed GitHub issue.
 *
 * Auth: caller must supply their Supabase JWT as `Authorization:
 * Bearer <token>`. The server verifies the token via Supabase and
 * confirms the user is admin (isAdmin(user.email)). Non-admins get
 * 403; missing/invalid tokens get 401.
 *
 * Body: { report: string, runId?: string } — `report` is the
 * paste-friendly text format produced by formatReport() in the
 * diagnostic-runner. Capped at 1MB.
 *
 * Behavior: posts the report as a comment on
 * github.com/<owner>/<repo>/issues/<issueNumber>, configured via env.
 * GitHub comments have a 65536-char body limit, so the report is
 * truncated with a marker if it exceeds ~60000 chars (leaving
 * headroom for the wrapper preamble).
 *
 * Setup (one-time, on Vercel):
 *   1. Create a fine-grained PAT at
 *      https://github.com/settings/tokens?type=beta
 *      Scope: repository khs/tape, permission "Issues: Read and write"
 *   2. Create a "Diagnostics" issue on the repo (any state — open or
 *      closed, doesn't matter for commenting). Note its number.
 *   3. Set Vercel env vars:
 *        GITHUB_TOKEN=<the PAT>
 *        GITHUB_DIAGNOSTIC_OWNER=khs            (defaults to "khs")
 *        GITHUB_DIAGNOSTIC_REPO=tape            (defaults to "tape")
 *        GITHUB_DIAGNOSTIC_ISSUE_NUMBER=<num>   (no default)
 *   4. Redeploy.
 *
 * Without those env vars set, the endpoint returns 500 with a
 * specific "X env var not set" error — visible to the admin in the
 * /me/diagnostics UI.
 */
import type { APIRoute } from "astro";
import { createClient } from "@supabase/supabase-js";
import { isAdmin } from "../../lib/admin";

export const prerender = false;

// Max comment body in GitHub is 65536 chars; reserve ~5000 for the
// header/footer we wrap around the report.
const MAX_REPORT_CHARS = 60000;
// Max request body the endpoint accepts, before truncation. Loose
// upper bound on what a runaway report could legitimately produce.
const MAX_REQUEST_BYTES = 1_000_000;

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export const POST: APIRoute = async ({ request, clientAddress }) => {
  // 1. Extract Bearer token.
  const authHeader = request.headers.get("Authorization") ?? "";
  const token = authHeader.startsWith("Bearer ")
    ? authHeader.slice("Bearer ".length).trim()
    : null;
  if (!token) {
    // A09: log auth failures server-side (captured in Vercel function
    // logs) so the app's one privileged endpoint isn't a blind spot.
    console.warn("[diagnostic] auth failure: missing bearer token");
    return jsonResponse(
      { error: "Missing Authorization: Bearer <token> header" },
      401,
    );
  }

  // 2. Verify token + check admin via Supabase.
  const supabaseUrl = import.meta.env.PUBLIC_SUPABASE_URL;
  const anonKey = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !anonKey) {
    return jsonResponse(
      { error: "Supabase env vars missing on the server" },
      500,
    );
  }
  const sb = createClient(supabaseUrl, anonKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  // 2a. Rate-limit by client IP BEFORE the Supabase auth round-trip. Without
  // this, anonymous token-spray forces a sb.auth.getUser() (auth-server call +
  // DB read) on every request, burning Supabase quota long before the admin
  // check below would reject the caller — classic authn-before-authz quota
  // drain. The diagnostic_rate_limit RPC (migration 0008) caps to 10/min/IP via
  // the shared check_rate_limit infra. It FAILS OPEN: if the RPC is missing
  // (migration not yet applied) the call errors and we log + continue, so the
  // endpoint keeps working — rate-limiting simply activates once 0008 lands.
  let clientIp = "unknown";
  try {
    if (clientAddress) clientIp = clientAddress;
  } catch {
    // Adapter without client-address support — bucket all as "unknown".
  }
  const { data: underLimit, error: rlErr } = await sb.rpc(
    "diagnostic_rate_limit",
    { p_ip: clientIp },
  );
  if (rlErr) {
    console.warn(
      `[diagnostic] rate-limit RPC unavailable, failing open: ${rlErr.message}`,
    );
  } else if (underLimit === false) {
    console.warn(`[diagnostic] rate-limited ip ${clientIp}`);
    return jsonResponse(
      { error: "Too many requests — try again in a minute." },
      429,
    );
  }

  const { data: userResult, error: authErr } = await sb.auth.getUser(token);
  if (authErr || !userResult?.user) {
    console.warn(
      `[diagnostic] auth failure: invalid token (${authErr?.message ?? "no user"})`,
    );
    return jsonResponse(
      { error: `Invalid token: ${authErr?.message ?? "no user"}` },
      401,
    );
  }
  const user = userResult.user;
  if (!isAdmin(user.email)) {
    // Don't leak the admin email or the rule in the RESPONSE; just refuse.
    // Do record the rejected identity server-side for the admin's audit.
    console.warn(
      `[diagnostic] authz failure: non-admin user ${user.email ?? "unknown"}`,
    );
    return jsonResponse({ error: "Not authorized" }, 403);
  }
  // Audit trail for the privileged action itself (the real replay-risk
  // path): a successful, authorized admin report post is recorded.
  console.log(`[diagnostic] authorized admin report by ${user.email}`);

  // 3. Validate request body.
  let body: { report?: unknown; runId?: unknown };
  try {
    const text = await request.text();
    if (text.length > MAX_REQUEST_BYTES) {
      return jsonResponse(
        { error: `Body too large (${text.length} > ${MAX_REQUEST_BYTES})` },
        413,
      );
    }
    body = JSON.parse(text);
  } catch (e) {
    return jsonResponse(
      { error: `Invalid JSON body: ${(e as Error).message}` },
      400,
    );
  }
  if (typeof body.report !== "string" || !body.report) {
    return jsonResponse(
      { error: "Missing or non-string `report` field" },
      400,
    );
  }
  const runId = typeof body.runId === "string" ? body.runId : null;

  // 4. Read GitHub config from env.
  const ghToken = process.env.GITHUB_TOKEN;
  const owner = process.env.GITHUB_DIAGNOSTIC_OWNER ?? "khs";
  const repo = process.env.GITHUB_DIAGNOSTIC_REPO ?? "tape";
  const issueNumber = process.env.GITHUB_DIAGNOSTIC_ISSUE_NUMBER;
  if (!ghToken) {
    return jsonResponse(
      {
        error:
          "GITHUB_TOKEN env var not set on Vercel. See src/pages/api/diagnostic.ts header for setup steps.",
      },
      500,
    );
  }
  if (!issueNumber) {
    return jsonResponse(
      {
        error:
          "GITHUB_DIAGNOSTIC_ISSUE_NUMBER env var not set. Create a 'Diagnostics' issue on the repo and set its number.",
      },
      500,
    );
  }

  // 5. Truncate report if it'd exceed the GitHub comment-body limit.
  let report = body.report;
  let truncatedBy = 0;
  if (report.length > MAX_REPORT_CHARS) {
    truncatedBy = report.length - MAX_REPORT_CHARS;
    report =
      report.slice(0, MAX_REPORT_CHARS) +
      `\n\n[…truncated ${truncatedBy} chars to fit GitHub's 65536-char comment limit. Download the full .txt locally for the complete report.]\n`;
  }

  const commentLines: string[] = [];
  commentLines.push(`## Diagnostic run`);
  commentLines.push("");
  if (runId) commentLines.push(`Run ID: \`${runId}\``);
  commentLines.push(`Posted by: ${user.email}`);
  commentLines.push(`Timestamp: ${new Date().toISOString()}`);
  if (truncatedBy > 0) {
    commentLines.push(
      `**Note:** report truncated by ${truncatedBy} chars to fit GitHub's comment-body limit.`,
    );
  }
  commentLines.push("");
  commentLines.push("```");
  commentLines.push(report);
  commentLines.push("```");
  const commentBody = commentLines.join("\n");

  // 6. POST the comment.
  const ghUrl = `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/comments`;
  let ghRes: Response;
  try {
    ghRes = await fetch(ghUrl, {
      method: "POST",
      headers: {
        Authorization: `token ${ghToken}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "tape-diagnostic-poster",
      },
      body: JSON.stringify({ body: commentBody }),
    });
  } catch (e) {
    return jsonResponse(
      { error: `Network error contacting GitHub: ${(e as Error).message}` },
      502,
    );
  }
  if (!ghRes.ok) {
    const errText = await ghRes.text().catch(() => "(no body)");
    return jsonResponse(
      {
        error: `GitHub API ${ghRes.status}: ${errText.slice(0, 500)}`,
        status: ghRes.status,
      },
      502,
    );
  }
  const comment = (await ghRes.json()) as {
    html_url?: string;
    id?: number;
  };
  return jsonResponse(
    {
      commentUrl: comment.html_url ?? null,
      commentId: comment.id ?? null,
      truncatedBy,
    },
    200,
  );
};
