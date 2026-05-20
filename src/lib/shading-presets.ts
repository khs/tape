/**
 * Background-shading presets for chart plots.
 *
 * A "shading" is a set of date bands rendered as semi-transparent
 * rectangles BEHIND the time-series line(s). Used to contextualize
 * a chart against a parallel timeline (recession periods, who held
 * the White House, etc.) without cluttering the foreground with
 * labels or text annotations.
 *
 * Each preset returns a list of bands; the renderer draws them via
 * Plot.rectX with low fillOpacity so the line stays readable. Bands
 * are deliberately stylized — the colour palette here is muted so
 * a chart with two stacked shadings (e.g. recessions + president
 * party) doesn't turn into a heat-map.
 *
 * Source notes:
 *   - NBER recessions: published authoritative list at
 *     https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions
 *     Updates when NBER's dating committee announces a new cycle —
 *     roughly every few years.
 *   - Presidential terms: trivial constant, updates every 2-4y.
 *   - Senate / House majorities: by Congress (odd-year January
 *     transitions). Updates after each November election.
 *   - Bear markets: S&P 500 drawdown >= 20% from prior peak. Drawn
 *     from the canonical list maintained by Yardeni Research /
 *     S&P Dow Jones Indices. Doesn't auto-extend; check on update.
 *   - Fed Chair tenures: trivial constant, updates at Chair turnover.
 */

/** ISO YYYY-MM-DD bounds for a single shaded band. */
export interface ShadingBand {
  start: string;
  end: string;
  /** Plot fill — keep muted so the line stays readable when stacked. */
  fill: string;
  /** Hover tooltip label. e.g. "2007-09 to 2009-06: GFC recession". */
  label: string;
}

export type ShadingKey =
  | "recessions"
  | "president_party"
  | "senate_majority"
  | "house_majority"
  | "bear_markets"
  | "fed_chairs";

/** Human-readable name for the composer's shading-picker UI. */
export const SHADING_LABELS: Record<ShadingKey, string> = {
  recessions: "NBER recessions",
  president_party: "Presidential party",
  senate_majority: "Senate majority",
  house_majority: "House majority",
  bear_markets: "S&P 500 bear markets",
  fed_chairs: "Fed Chair tenures",
};

/**
 * Short description shown in the composer next to each option —
 * helps disambiguate when two shadings sound similar (presidential
 * party vs. congressional control).
 */
export const SHADING_DESCRIPTIONS: Record<ShadingKey, string> = {
  recessions:
    "Gray bands during NBER-dated US recessions (1945-present).",
  president_party:
    "Blue bands during Democratic presidencies; red during Republican.",
  senate_majority:
    "Blue / red bands by which party held the Senate majority.",
  house_majority:
    "Blue / red bands by which party held the House majority.",
  bear_markets:
    "S&P 500 drawdowns of at least 20% from prior peak.",
  fed_chairs:
    "Muted bands by Federal Reserve Chair tenure (Volcker onward).",
};

// Muted palette. Recessions = neutral gray; party shadings tinted so
// stacking with recessions stays legible.
const FILL_RECESSION = "#9CA3AF";
const FILL_DEM = "#3B82F6";
const FILL_REP = "#EF4444";
const FILL_BEAR = "#A855F7";
const FILL_CHAIR_A = "#94A3B8";
const FILL_CHAIR_B = "#CBD5E1";

/**
 * NBER-dated US business-cycle contractions since 1945. ISO start =
 * peak month start; ISO end = trough month end (inclusive of the
 * trough month). When the dating committee adds a new cycle, append
 * here.
 */
const NBER_RECESSIONS: ShadingBand[] = [
  { start: "1945-02-01", end: "1945-10-31", fill: FILL_RECESSION, label: "1945: post-WWII reconversion" },
  { start: "1948-11-01", end: "1949-10-31", fill: FILL_RECESSION, label: "1948-49 recession" },
  { start: "1953-07-01", end: "1954-05-31", fill: FILL_RECESSION, label: "1953-54 recession" },
  { start: "1957-08-01", end: "1958-04-30", fill: FILL_RECESSION, label: "1957-58 recession" },
  { start: "1960-04-01", end: "1961-02-28", fill: FILL_RECESSION, label: "1960-61 recession" },
  { start: "1969-12-01", end: "1970-11-30", fill: FILL_RECESSION, label: "1969-70 recession" },
  { start: "1973-11-01", end: "1975-03-31", fill: FILL_RECESSION, label: "1973-75 oil shock" },
  { start: "1980-01-01", end: "1980-07-31", fill: FILL_RECESSION, label: "1980 recession" },
  { start: "1981-07-01", end: "1982-11-30", fill: FILL_RECESSION, label: "1981-82 Volcker recession" },
  { start: "1990-07-01", end: "1991-03-31", fill: FILL_RECESSION, label: "1990-91 recession" },
  { start: "2001-03-01", end: "2001-11-30", fill: FILL_RECESSION, label: "2001 dot-com bust" },
  { start: "2007-12-01", end: "2009-06-30", fill: FILL_RECESSION, label: "2007-09 Great Recession" },
  { start: "2020-02-01", end: "2020-04-30", fill: FILL_RECESSION, label: "2020 COVID recession" },
];

/**
 * S&P 500 bear markets — drawdowns of at least 20% from prior peak.
 * Distinct from NBER recessions; the 1987 crash and 2022 inflation
 * bear aren't NBER-dated, while the 1945 / 1960 recessions don't
 * coincide with bear markets.
 */
const BEAR_MARKETS: ShadingBand[] = [
  { start: "1973-01-11", end: "1974-10-03", fill: FILL_BEAR, label: "1973-74 bear (-48%)" },
  { start: "1980-11-28", end: "1982-08-12", fill: FILL_BEAR, label: "1980-82 bear (-27%)" },
  { start: "1987-08-25", end: "1987-12-04", fill: FILL_BEAR, label: "1987 Black Monday (-34%)" },
  { start: "1990-07-16", end: "1990-10-11", fill: FILL_BEAR, label: "1990 bear (-20%)" },
  { start: "2000-03-24", end: "2002-10-09", fill: FILL_BEAR, label: "2000-02 dot-com bust (-49%)" },
  { start: "2007-10-09", end: "2009-03-09", fill: FILL_BEAR, label: "2007-09 GFC bear (-57%)" },
  { start: "2020-02-19", end: "2020-03-23", fill: FILL_BEAR, label: "2020 COVID crash (-34%)" },
  { start: "2022-01-03", end: "2022-10-12", fill: FILL_BEAR, label: "2022 inflation bear (-25%)" },
];

/**
 * Presidential terms since FDR. Each entry is a continuous occupant
 * (so e.g. Truman starts on FDR's death, not via inauguration).
 * `party` is the renderer's color key; "D" → blue, "R" → red.
 */
const PRESIDENT_TERMS: { start: string; end: string; name: string; party: "D" | "R" }[] = [
  { start: "1933-03-04", end: "1945-04-12", name: "FDR", party: "D" },
  { start: "1945-04-12", end: "1953-01-20", name: "Truman", party: "D" },
  { start: "1953-01-20", end: "1961-01-20", name: "Eisenhower", party: "R" },
  { start: "1961-01-20", end: "1963-11-22", name: "Kennedy", party: "D" },
  { start: "1963-11-22", end: "1969-01-20", name: "L. Johnson", party: "D" },
  { start: "1969-01-20", end: "1974-08-09", name: "Nixon", party: "R" },
  { start: "1974-08-09", end: "1977-01-20", name: "Ford", party: "R" },
  { start: "1977-01-20", end: "1981-01-20", name: "Carter", party: "D" },
  { start: "1981-01-20", end: "1989-01-20", name: "Reagan", party: "R" },
  { start: "1989-01-20", end: "1993-01-20", name: "G.H.W. Bush", party: "R" },
  { start: "1993-01-20", end: "2001-01-20", name: "Clinton", party: "D" },
  { start: "2001-01-20", end: "2009-01-20", name: "G.W. Bush", party: "R" },
  { start: "2009-01-20", end: "2017-01-20", name: "Obama", party: "D" },
  { start: "2017-01-20", end: "2021-01-20", name: "Trump (1st)", party: "R" },
  { start: "2021-01-20", end: "2025-01-20", name: "Biden", party: "D" },
  { start: "2025-01-20", end: "2029-01-20", name: "Trump (2nd)", party: "R" },
];

/**
 * Senate majority by Congress, 80th onward (Jan 1947).
 * Each Congress starts Jan 3 of odd years; end = next Congress start.
 * `party` "D" / "R" — third-party caucusing is folded into whoever
 * provided the organizing-majority votes (Sanders, King → D).
 */
const SENATE_MAJORITY: { start: string; end: string; congress: number; party: "D" | "R" }[] = [
  { start: "1947-01-03", end: "1949-01-03", congress: 80, party: "R" },
  { start: "1949-01-03", end: "1953-01-03", congress: 81, party: "D" },
  { start: "1953-01-03", end: "1955-01-03", congress: 83, party: "R" },
  { start: "1955-01-03", end: "1981-01-03", congress: 84, party: "D" },
  { start: "1981-01-03", end: "1987-01-03", congress: 97, party: "R" },
  { start: "1987-01-03", end: "1995-01-03", congress: 100, party: "D" },
  { start: "1995-01-03", end: "2001-01-03", congress: 104, party: "R" },
  { start: "2001-01-03", end: "2001-06-06", congress: 107, party: "R" }, // Jeffords switch
  { start: "2001-06-06", end: "2003-01-03", congress: 107, party: "D" },
  { start: "2003-01-03", end: "2007-01-03", congress: 108, party: "R" },
  { start: "2007-01-03", end: "2015-01-03", congress: 110, party: "D" },
  { start: "2015-01-03", end: "2021-01-20", congress: 114, party: "R" },
  { start: "2021-01-20", end: "2025-01-03", congress: 117, party: "D" },
  { start: "2025-01-03", end: "2027-01-03", congress: 119, party: "R" },
];

/** House majority by Congress, 80th onward. */
const HOUSE_MAJORITY: { start: string; end: string; congress: number; party: "D" | "R" }[] = [
  { start: "1947-01-03", end: "1949-01-03", congress: 80, party: "R" },
  { start: "1949-01-03", end: "1953-01-03", congress: 81, party: "D" },
  { start: "1953-01-03", end: "1955-01-03", congress: 83, party: "R" },
  { start: "1955-01-03", end: "1995-01-03", congress: 84, party: "D" },
  { start: "1995-01-03", end: "2007-01-03", congress: 104, party: "R" },
  { start: "2007-01-03", end: "2011-01-03", congress: 110, party: "D" },
  { start: "2011-01-03", end: "2019-01-03", congress: 112, party: "R" },
  { start: "2019-01-03", end: "2023-01-03", congress: 116, party: "D" },
  { start: "2023-01-03", end: "2027-01-03", congress: 118, party: "R" },
];

/** Fed Chair tenures, Volcker onward (1979). Alternating colors per chair. */
const FED_CHAIRS: { start: string; end: string; name: string }[] = [
  { start: "1979-08-06", end: "1987-08-11", name: "Volcker" },
  { start: "1987-08-11", end: "2006-01-31", name: "Greenspan" },
  { start: "2006-02-01", end: "2014-01-31", name: "Bernanke" },
  { start: "2014-02-03", end: "2018-02-03", name: "Yellen" },
  { start: "2018-02-05", end: "2030-05-15", name: "Powell" },
];

function partyFill(party: "D" | "R"): string {
  return party === "D" ? FILL_DEM : FILL_REP;
}

function partyLabel(party: "D" | "R"): string {
  return party === "D" ? "Democratic" : "Republican";
}

/**
 * Resolve a shading key to a list of date bands. Returns an empty
 * list for unknown keys (forward-compatible: a saved dashboard
 * referencing a shading key we don't recognize just renders without
 * the bands rather than erroring).
 */
export function bandsFor(key: ShadingKey): ShadingBand[] {
  switch (key) {
    case "recessions":
      return NBER_RECESSIONS;
    case "bear_markets":
      return BEAR_MARKETS;
    case "president_party":
      return PRESIDENT_TERMS.map((t) => ({
        start: t.start,
        end: t.end,
        fill: partyFill(t.party),
        label: `${t.name} (${partyLabel(t.party)})`,
      }));
    case "senate_majority":
      return SENATE_MAJORITY.map((t) => ({
        start: t.start,
        end: t.end,
        fill: partyFill(t.party),
        label: `${t.congress}th Congress: ${partyLabel(t.party)} Senate`,
      }));
    case "house_majority":
      return HOUSE_MAJORITY.map((t) => ({
        start: t.start,
        end: t.end,
        fill: partyFill(t.party),
        label: `${t.congress}th Congress: ${partyLabel(t.party)} House`,
      }));
    case "fed_chairs":
      return FED_CHAIRS.map((t, i) => ({
        start: t.start,
        end: t.end,
        fill: i % 2 === 0 ? FILL_CHAIR_A : FILL_CHAIR_B,
        label: `Fed Chair: ${t.name}`,
      }));
    default:
      return [];
  }
}

/**
 * Fill opacity for a single shading layer. When multiple shadings
 * are stacked on one chart (e.g. recessions + president-party), the
 * renderer applies this opacity per layer; intersections darken
 * naturally via alpha compositing.
 *
 * Tuned to keep the underlying line clearly visible — bands should
 * feel like context, not foreground.
 */
export const SHADING_FILL_OPACITY = 0.12;
