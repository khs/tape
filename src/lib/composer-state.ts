import { z } from "zod";
import { DELTA_WINDOWS, type DeltaWindow } from "./deltas";

/**
 * Schema version for composed-dashboard URL state. Bump this whenever the
 * shape changes incompatibly; the /custom/ renderer shows an error banner when
 * the incoming `v` doesn't match and asks the user to re-fork.
 */
export const COMPOSER_STATE_VERSION = 1 as const;

const deltaWindowSchema = z.enum(DELTA_WINDOWS as unknown as [DeltaWindow, ...DeltaWindow[]]);

const chartOverrideSchema = z
  .object({
    title: z.string(),
    defaultDelta: deltaWindowSchema,
    blurb: z.string(),
  })
  .partial();

const sectionSchema = z.object({
  title: z.string(),
  description: z.string().optional(),
  charts: z.array(z.string()).min(1),
});

export const composedStateSchema = z.object({
  v: z.literal(COMPOSER_STATE_VERSION),
  title: z.string().optional(),
  description: z.string().optional(),
  defaultDelta: deltaWindowSchema.optional(),
  charts: z.array(z.string()).optional(),
  sections: z.array(sectionSchema).optional(),
  chartOverrides: z.record(z.string(), chartOverrideSchema).optional(),
});

export type ComposedState = z.infer<typeof composedStateSchema>;

/** Base64url encode without padding (URL-safe). */
function base64urlEncode(input: string): string {
  // TextEncoder -> bytes -> base64 -> base64url (replace / + and strip =)
  const bytes = new TextEncoder().encode(input);
  let b64: string;
  // Browser-compatible path when available.
  if (typeof btoa !== "undefined") {
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    b64 = btoa(bin);
  } else {
    // Node fallback.
    b64 = Buffer.from(bytes).toString("base64");
  }
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlDecode(input: string): string {
  const pad = input.length % 4 === 0 ? "" : "=".repeat(4 - (input.length % 4));
  const b64 = input.replace(/-/g, "+").replace(/_/g, "/") + pad;
  if (typeof atob !== "undefined") {
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }
  return Buffer.from(b64, "base64").toString("utf-8");
}

/**
 * Encode a composed dashboard's state into the `?d=...` URL param.
 * Accepts a partial input; stamps the current version automatically.
 */
export function encodeComposedState(
  partial: Omit<ComposedState, "v"> & Partial<Pick<ComposedState, "v">>,
): string {
  const full: ComposedState = { v: COMPOSER_STATE_VERSION, ...partial };
  // Strip undefined values so the JSON stays compact.
  const clean = JSON.parse(JSON.stringify(full));
  return base64urlEncode(JSON.stringify(clean));
}

export type DecodeResult =
  | { ok: true; state: ComposedState }
  | { ok: false; reason: "empty" | "invalid-encoding" | "invalid-shape" | "wrong-version"; message: string };

/**
 * Decode + Zod-validate a `?d=...` value. Callers should pattern-match on
 * `ok` and render an error panel when decode fails.
 */
export function decodeComposedState(raw: string | null | undefined): DecodeResult {
  if (!raw) return { ok: false, reason: "empty", message: "No composition provided." };
  let json: string;
  try {
    json = base64urlDecode(raw);
  } catch (e) {
    return { ok: false, reason: "invalid-encoding", message: "Composition link is malformed." };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return { ok: false, reason: "invalid-encoding", message: "Composition JSON is corrupted." };
  }
  const maybe = composedStateSchema.safeParse(parsed);
  if (!maybe.success) {
    const obj = parsed as { v?: unknown };
    if (typeof obj?.v === "number" && obj.v !== COMPOSER_STATE_VERSION) {
      return {
        ok: false,
        reason: "wrong-version",
        message: `This composition was created with a different version (v${obj.v}). Please re-fork or re-compose.`,
      };
    }
    return { ok: false, reason: "invalid-shape", message: "Composition doesn't match the expected shape." };
  }
  return { ok: true, state: maybe.data };
}
