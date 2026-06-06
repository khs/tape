// Remove stale build output before a build.
//
// Why this exists: if a local `astro build` is interrupted partway through
// (laptop sleep, lid-close, Ctrl-C, OOM kill), it can leave a partial/corrupt
// `dist/`. The next build's Vite `prepareOutDir` step empties the old directory
// by stat-ing every entry, and throws on a half-written one — the failure looks
// like:
//
//   at Object.statSync (node:fs)
//   at copyDir (.../vite/.../dep-*.js)
//   at prepareOutDir (.../vite/.../dep-*.js)
//   at async clientBuild (astro/.../static-build.js)
//
// …which aborts the whole build for no obvious reason. Removing the output dirs
// up front — robustly, with retries for transient Windows file locks — sidesteps
// that entirely, so an interrupted build never poisons the next one. On CI /
// Vercel the dirs are absent on a fresh checkout, so this is a no-op there.
//
// Runs automatically via the `prebuild` npm hook (see package.json). It removes
// only `.vercel/output` (the build output), never `.vercel/project.json` (the
// Vercel project link).
import { rmSync } from "node:fs";

const targets = ["dist", ".vercel/output"];

for (const dir of targets) {
  try {
    rmSync(dir, {
      recursive: true,
      force: true, // no error if the dir doesn't exist
      maxRetries: 5, // ride out transient EBUSY/EPERM locks (common on Windows)
      retryDelay: 200,
    });
    console.log(`[clean] cleared ${dir}`);
  } catch (err) {
    // Best-effort: if removal still fails, warn but let the build's own
    // empty-outDir step try — its error (or success) is more informative than
    // aborting here.
    console.warn(`[clean] could not remove ${dir}: ${err.message}`);
  }
}
