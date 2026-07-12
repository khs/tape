/**
 * Types for the framework-agnostic page-checks.mjs core. Hand-written because
 * the core is plain ESM JS (so the dependency-free Node runner can import it),
 * but its TypeScript consumer (page-tests.ts) still gets full type safety.
 */
import type { DiagnosticResult } from "../diagnostic-runner";

/** Result of one HTTP GET, as the host's `ctx.get` returns it. */
export interface PageGetResult {
  status: number;
  contentType: string | null;
  cacheControl: string | null;
  body: string;
}

/** Result of one binary GET, as the host's `ctx.getBuffer` returns it. */
export interface PageBufferResult {
  status: number;
  contentType: string | null;
  bytes: number;
}

/**
 * The host-supplied fetch context. The browser wrapper resolves paths against
 * `window.location.origin`; the Node runner resolves them against the target
 * URL. Both keep the check bodies free of any origin/global.
 */
export interface PageCheckCtx {
  get(pathOrUrl: string): Promise<PageGetResult>;
  getBuffer(pathOrUrl: string): Promise<PageBufferResult>;
  /** A per-run unique token for cache-busting paths (the host injects it so
   *  the core stays pure — e.g. Date.now()). */
  nonce: string | number;
}

/** One page-fetch check. Mirrors DiagnosticTest but its `run` takes a ctx. */
export interface PageCheck {
  id: string;
  label: string;
  category: string;
  timeoutMs?: number;
  run(ctx: PageCheckCtx): Promise<DiagnosticResult>;
}

export declare const pageChecks: PageCheck[];
