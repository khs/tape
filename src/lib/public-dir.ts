import path from "node:path";

/**
 * Build/dev base path for reads under public/ whose sub-path is DYNAMIC
 * (load-data's `data/<source>.json`, ChartMap's boundary/data files + vintage
 * readdir). Those reads use `process.cwd() + "/public/" + <variable>`, which
 * node-file-trace can't resolve — so it conservatively bundles the ENTIRE
 * public/ tree (705MB data + 219MB maps) into the Vercel serverless function.
 * The astro.config strip hook then deletes it post-build, but the ~924MB
 * copy-then-delete is wasted build I/O (~167s of the build).
 *
 * Sourcing the base from an env var (set by astro.config, see
 * `process.env.TAPE_PUBLIC_DIR`) keeps the path opaque to node-file-trace, so
 * it bundles nothing for these reads. Safe because at FUNCTION RUNTIME these
 * fs reads never execute — `isServerlessRuntime()` routes to an HTTPS fetch
 * against the deployment's static assets (load-data.ts / ChartMap), or the
 * read degrades gracefully (the vintage readdir is wrapped in try/catch). The
 * env var is unset at runtime, which is fine for exactly that reason.
 *
 * Reads with a FIXED sub-path (og.png's node_modules fonts,
 * build-library-manifest's single source_index.json) are intentionally NOT
 * routed through here — node-file-trace bundles only their specific small
 * files, which is correct.
 */
export function publicFilePath(...segments: string[]): string {
  const base = process.env.TAPE_PUBLIC_DIR;
  if (!base) {
    // Only reachable if a public/ fs read runs outside the astro build/dev
    // process (which sets the var). Fail loud rather than path.join(undefined).
    throw new Error(
      "TAPE_PUBLIC_DIR is unset — astro.config.mjs sets it for build/dev " +
        "public/ reads; at serverless runtime these reads should not run.",
    );
  }
  return path.join(base, ...segments);
}
