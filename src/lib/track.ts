// Custom-event tracking wrapper.
//
// Why this file exists:
//   Vercel Web Analytics' track() silently drops custom events on the Hobby
//   tier (you only get pageviews). We want full custom-event visibility, so
//   custom events get routed to PostHog instead. Vercel's <Analytics />
//   pageview injection still runs separately from BaseLayout — that piece
//   works on Hobby and is free.
//
// Configuration:
//   PUBLIC_POSTHOG_KEY  - the Project API Key (phc_xxx). PUBLIC_ prefix is
//                         required for Astro to expose it to client bundles.
//   PUBLIC_POSTHOG_HOST - usually https://us.i.posthog.com or
//                         https://eu.i.posthog.com. Defaults to US cloud.
//
// When PUBLIC_POSTHOG_KEY is empty (local dev without it, preview builds
// before the env var lands, etc.) every track() call no-ops cleanly — no
// console errors, no thrown exceptions, no network noise.
//
// Pageview capture is DISABLED on init because Vercel Web Analytics already
// records pageviews; double-counting would inflate session counts and
// confuse anyone reading either dashboard.

import posthog from "posthog-js";

type Props = Record<string, string | number | boolean | null | undefined>;

const KEY = import.meta.env.PUBLIC_POSTHOG_KEY as string | undefined;
const HOST =
  (import.meta.env.PUBLIC_POSTHOG_HOST as string | undefined) ??
  "https://us.i.posthog.com";

let initialized = false;
let initAttempted = false;

function ensureInit(): boolean {
  if (initialized) return true;
  if (initAttempted) return false; // already failed once; don't retry
  initAttempted = true;
  if (typeof window === "undefined") return false; // SSR guard
  if (!KEY) return false; // unconfigured environment

  try {
    posthog.init(KEY, {
      api_host: HOST,
      // Vercel handles pageviews; opt out here to avoid duplicate counts.
      capture_pageview: false,
      // We don't currently use session replay (privacy-sensitive, and we
      // have no UX-debugging need). Cheap to flip on later if useful.
      disable_session_recording: true,
      // Persistence: anonymous-cookie + localStorage. Same default cookie
      // as posthog-js standard; we never identify users so this is just
      // a stable anonymous distinct_id across sessions.
      persistence: "localStorage+cookie",
      // Quiet logs in production; PostHog defaults to noisy on init.
      loaded: () => {
        initialized = true;
      },
    });
    // posthog.init's loaded callback is async, but the SDK already queues
    // capture() calls made before init completes. Flag as initialized
    // synchronously so callers don't re-attempt.
    initialized = true;
    return true;
  } catch (e) {
    // Defensive — bad key, blocked host, etc. Don't let analytics crash
    // the page.
    if (typeof console !== "undefined") {
      console.warn("[track] PostHog init failed:", e);
    }
    return false;
  }
}

/**
 * Fire a custom analytics event. Safe to call from anywhere in the client
 * bundle; no-ops gracefully when PostHog isn't configured or on SSR.
 */
export function track(event: string, props?: Props): void {
  if (!ensureInit()) return;
  try {
    posthog.capture(event, props);
  } catch (e) {
    if (typeof console !== "undefined") {
      console.warn(`[track] capture('${event}') failed:`, e);
    }
  }
}

/** Whether tracking is actually wired up — useful for conditional UI. */
export function isTrackingConfigured(): boolean {
  return Boolean(KEY);
}
