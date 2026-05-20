/**
 * First-sign-in tutorial seeder.
 *
 * When a user signs in and has no saved dashboards yet, drop a copy of
 * the walkthrough dashboard into their account titled "Tutorial". They
 * can then explore the features by clicking around their own copy
 * (renaming sections, deleting tiles, etc.) without affecting the
 * shared /walkthrough/ page that the marketing pitch links to.
 *
 * Guarantees:
 *   1. Never re-creates the Tutorial if a user deletes it (a localStorage
 *      flag is set the first time we attempt the seed and short-circuits
 *      future sign-ins on the same browser).
 *   2. Never seeds for a user who already has saved dashboards — the
 *      explicit "no rows yet" check filters out returning users who hit
 *      this code from a new browser.
 *   3. Failure modes degrade safely: a network error during the
 *      empty-check or the insert leaves the flag UNSET so the next
 *      sign-in retries.
 *
 * The TUTORIAL_STATE constant below mirrors the curated walkthrough
 * dashboard. If walkthrough.mdx changes structurally, this should be
 * updated in lockstep — the seed runs once per account, so existing
 * users won't see drifted copies, but new users should get the latest
 * feature set.
 */
import { nanoid } from "nanoid";
import {
  SUPABASE_REST_URL,
  SUPABASE_REST_ANON_KEY,
  type StoredSession,
} from "./supabase";
import type { ComposedState } from "./composer-state";

const FLAG_PREFIX = "tape:seeded-tutorial:";

const TUTORIAL_STATE: ComposedState = {
  v: 1,
  title: "Tutorial",
  defaultDelta: "1y",
  description:
    "Your personal copy of the Tape walkthrough — feel free to edit, " +
    "rename sections, swap tiles, or delete it entirely. Each section " +
    "below demos a different Tape feature.",
  sections: [
    {
      title: "Every mini-chart shows the level and the change",
      description:
        "The big number is today's value; the small number is how it's " +
        "changed across the current window (set by the options above). " +
        "You can also click any of them to expand: try it on US " +
        "unemployment rate to find out more.",
      charts: [
        "us-macro/unemployment_walkthrough",
        "us-macro/ten_year",
        "us-macro/sp500",
      ],
    },
    {
      title: "Same data, different windows",
      description:
        "The dashboard-wide pills above (1W, 1M, YTD, 1Y, 5Y, 10Y, 30Y, " +
        "50Y) flip every tile to that lookback in lockstep. A section can " +
        "pin its own window — these three render at 30Y regardless of " +
        "where the top pills are set.",
      defaultDelta: "30y",
      charts: [
        "us-macro/real_gdp",
        "us-macro/fed_funds",
        "us-macro/core_cpi",
      ],
    },
    {
      title: "Multi-source charts: combine series with math",
      description:
        "A tile can combine two or more series via the composer's " +
        "'+ Custom chart' or '+ Derived source' button. Pick an " +
        "operator (sum / difference / division) to collapse the inputs " +
        "into one derived line — addition (misery index = inflation + " +
        "unemployment), subtraction (yield-curve recession signal = 10Y " +
        "minus fed funds), or division (real GDP per capita).",
      charts: [
        "us-macro/misery_index",
        "us-macro/yield_curve_spread",
        "us-macro/real_gdp_per_capita",
      ],
    },
    {
      title: "Forecasts ship as a dashed line",
      description:
        "When a series has an official projection, it renders as a " +
        "dashed extension of the historical line — same axis, same " +
        "tooltip, no extra controls. Same treatment for futures curves " +
        "(oil, VIX, ag commodities) and the Social Security trustees' " +
        "OASDI projection.",
      charts: ["government/cbo_deficit_pct_gdp"],
    },
    {
      title: "Maps: choropleths at four resolutions",
      description:
        "Census ACS demographic data renders as interactive choropleth " +
        "maps at four geographic scales: state, county (~3,140), tract " +
        "(~500–9,000 per state), and block group (up to ~30,000 per " +
        "state). Click any region for the value + name.",
      charts: [
        "government/us_median_hh_income_county_map_2022",
        "government/us_poverty_rate_county_map_2022",
      ],
    },
    {
      title: "Multi-state regions",
      description:
        "Tract and block-group maps can stitch up to 4 states into one " +
        "regional view. The DMV tract map below combines VA, MD, and DC.",
      charts: ["government/dmv_median_hh_income_tract_map_2022"],
    },
  ],
};

/**
 * Idempotent. Called from BaseLayout's auth handler on every refresh
 * that detects a signed-in session; the localStorage flag short-circuits
 * repeat calls cheaply.
 */
export async function maybeSeedTutorial(
  stored: StoredSession,
): Promise<void> {
  if (!SUPABASE_REST_URL || !SUPABASE_REST_ANON_KEY) return;
  if (typeof localStorage === "undefined") return;

  const flagKey = `${FLAG_PREFIX}${stored.user.id}`;
  if (localStorage.getItem(flagKey)) return;

  // Cheap REST head: "do you have anything saved yet?". Anyone who
  // already has a dashboard (returning user, new browser) gets the flag
  // set so we never retry the seed.
  let hasAny: boolean;
  try {
    const url =
      `${SUPABASE_REST_URL}/rest/v1/saved_dashboards` +
      `?owner_id=eq.${encodeURIComponent(stored.user.id)}` +
      `&select=id&limit=1`;
    const res = await fetch(url, {
      headers: {
        apikey: SUPABASE_REST_ANON_KEY,
        Authorization: `Bearer ${stored.access_token}`,
      },
    });
    if (!res.ok) return;
    const rows = await res.json().catch(() => []);
    hasAny = Array.isArray(rows) && rows.length > 0;
  } catch {
    return;
  }

  if (hasAny) {
    try {
      localStorage.setItem(flagKey, "skip");
    } catch {
      /* localStorage quota or disabled — best-effort flag, swallow */
    }
    return;
  }

  // Empty list: seed.
  try {
    const insertRes = await fetch(
      `${SUPABASE_REST_URL}/rest/v1/saved_dashboards`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          apikey: SUPABASE_REST_ANON_KEY,
          Authorization: `Bearer ${stored.access_token}`,
          Prefer: "return=minimal",
        },
        body: JSON.stringify({
          slug: nanoid(10),
          owner_id: stored.user.id,
          title: TUTORIAL_STATE.title,
          state_json: TUTORIAL_STATE,
          // Private by default — the user can flip to public from /me/
          // if they want a shareable link. Their copy isn't useful to
          // strangers; the canonical walkthrough lives at /walkthrough/.
          visibility: "private",
        }),
      },
    );
    if (insertRes.ok) {
      try {
        localStorage.setItem(flagKey, "seeded");
      } catch {
        /* swallow */
      }
    }
  } catch {
    // Swallow; next sign-in retries.
  }
}
