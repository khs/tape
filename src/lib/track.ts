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

// posthog-js is loaded LAZILY (dynamic import inside ensureInit) so its ~188KB
// bundle stays OFF the synchronous critical path of every page that mounts a
// chart — it is fetched once the first track() call actually fires in a
// configured environment. Analytics is fire-and-forget, so the deferral is
// invisible; in an unconfigured environment (no PUBLIC_POSTHOG_KEY) the chunk
// is never requested at all.
type PostHog = (typeof import("posthog-js"))["default"];
let posthog: PostHog | null = null;

type Props = Record<string, string | number | boolean | null | undefined>;

const KEY = import.meta.env.PUBLIC_POSTHOG_KEY as string | undefined;
const HOST =
  (import.meta.env.PUBLIC_POSTHOG_HOST as string | undefined) ??
  "https://us.i.posthog.com";

let initialized = false;
let initPromise: Promise<boolean> | null = null;

function ensureInit(): Promise<boolean> {
  if (initialized) return Promise.resolve(true);
  if (initPromise) return initPromise; // load already in flight or settled
  if (typeof window === "undefined") return Promise.resolve(false); // SSR guard
  if (!KEY) return Promise.resolve(false); // unconfigured: never fetch the chunk

  initPromise = (async () => {
    try {
      // Dynamic import keeps the ~188KB posthog-js bundle off the synchronous
      // critical path; it is fetched only here, on the first real track() call
      // in a configured environment.
      const mod = await import("posthog-js");
      posthog = mod.default;
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
      });
      initialized = true;
      return true;
    } catch (e) {
      // Defensive — bad key, blocked host, failed chunk fetch, etc. Don't let
      // analytics crash the page.
      if (typeof console !== "undefined") {
        console.warn("[track] PostHog init failed:", e);
      }
      return false;
    }
  })();
  return initPromise;
}

/**
 * Fire a custom analytics event. Safe to call from anywhere in the client
 * bundle; no-ops gracefully when PostHog isn't configured or on SSR.
 */
export function track(event: string, props?: Props): void {
  // Fire-and-forget: ensureInit() resolves once posthog-js has loaded + init'd
  // (or immediately false when unconfigured / on SSR). We never block the
  // caller, and concurrent early calls share one in-flight load via initPromise.
  void ensureInit().then((ok) => {
    if (!ok || !posthog) return;
    try {
      posthog.capture(event, props);
    } catch (e) {
      if (typeof console !== "undefined") {
        console.warn(`[track] capture('${event}') failed:`, e);
      }
    }
  });
}

/** Whether tracking is actually wired up — useful for conditional UI. */
export function isTrackingConfigured(): boolean {
  return Boolean(KEY);
}
