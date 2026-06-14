/**
 * Data-integrity gate over the REAL referenced corpus.
 *
 * This is the suite that should have existed before oecd/jpn_cpi_yoy froze:
 * it walks every source a live chart actually renders and asserts the
 * structural + summary + referential invariants hold, failing the CI merge
 * if any chart would render blank, broken, or inconsistent. Freshness (the
 * "frozen but well-formed" class) is a separate concern — see
 * data-freshness.test.ts.
 *
 * Scope = referenced sources + all chart/dashboard YAMLs (a few seconds).
 * The full 34k/38k catalog deep scan stays in
 * scripts/audit-source-data.mjs --full (CI, report-only).
 *
 * Each check collects offenders into a list and asserts it is empty, so a
 * failure prints exactly which sources/charts are wrong rather than dying
 * on the first one.
 */
import { describe, it, expect } from "vitest";
import { existsSync } from "node:fs";
import { basename } from "node:path";
import {
  charts,
  dashboards,
  isLiveChart,
  referencedSources,
  sourceIds,
  dataPath,
  summaryPath,
  readJson,
  isTimeseries,
  points,
  lastPoint,
  DELTA_WINDOWS,
  ISO_DATE,
} from "./corpus";

type Json = Record<string, any>;
interface Loaded {
  id: string;
  dataFile: string;
  data: Json;
  summary: Json | null;
}

// Load each referenced time-series data file (+ its summary) exactly once.
const loaded: Loaded[] = [];
for (const s of referencedSources()) {
  if (!s.dataFile) continue;
  const fp = dataPath(s.dataFile);
  if (!existsSync(fp)) continue;
  const data = readJson(fp) as Json;
  if (!isTimeseries(data)) continue; // choropleth handled in referential block
  const sp = summaryPath(s.dataFile);
  loaded.push({
    id: s.id,
    dataFile: s.dataFile,
    data,
    summary: existsSync(sp) ? (readJson(sp) as Json) : null,
  });
}

const show = (bad: string[]) => `\n  ${bad.join("\n  ")}\n`;

describe("structural integrity (referenced time-series)", () => {
  it("renders: >= 2 historical points, or >= 1 projection point", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      const nHist = points(l.data).length;
      let nProj = 0;
      const proj = l.data.projections;
      if (proj && typeof proj === "object") {
        for (const arr of Object.values(proj)) {
          if (Array.isArray(arr)) nProj += arr.length;
        }
      }
      if (nHist + nProj < 2) {
        bad.push(`${l.id}: only ${nHist} points + ${nProj} projection points`);
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("dates are ISO YYYY-MM-DD, strictly ascending, no duplicates", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      const pts = points(l.data);
      let prev = "";
      for (const p of pts) {
        if (typeof p.t !== "string" || !ISO_DATE.test(p.t)) {
          bad.push(`${l.id}: non-ISO date ${JSON.stringify(p.t)}`);
          break;
        }
        if (prev && p.t <= prev) {
          bad.push(`${l.id}: out-of-order/duplicate date ${prev} -> ${p.t}`);
          break;
        }
        prev = p.t;
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("every value is a finite number (no null / NaN / Infinity / string)", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      for (const p of points(l.data)) {
        if (typeof p.v !== "number" || !Number.isFinite(p.v)) {
          bad.push(`${l.id}: bad value ${JSON.stringify(p.v)} at ${p.t}`);
          break;
        }
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("lastUpdated, when present, is a valid ISO instant", () => {
    // NB: we deliberately do NOT assert lastUpdated >= the last point's
    // date. Two legitimate conventions break that: futures-curve spot
    // points are dated month-END (e.g. 2026-05-31 from a 2026-05-28 fetch),
    // and usaspending's partial-FY annualization intentionally dates the
    // annualized point at the fiscal-year end (2026-09-30). lastUpdated is
    // the pipeline RUN time, not a data-vintage bound.
    const bad: string[] = [];
    for (const l of loaded) {
      const lu = l.data.lastUpdated;
      if (typeof lu !== "string") continue;
      if (Number.isNaN(Date.parse(lu))) {
        bad.push(`${l.id}: unparseable lastUpdated ${JSON.stringify(lu)}`);
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });
});

describe("summary consistency (referenced time-series)", () => {
  it("summary.latest equals the data file's last point", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      if (!l.summary) continue;
      const last = lastPoint(l.data);
      const latest = l.summary.latest as Json | undefined;
      if (!last || !latest) continue;
      if (latest.t !== last.t || latest.v !== last.v) {
        bad.push(
          `${l.id}: summary.latest ${JSON.stringify(latest)} != last point ${JSON.stringify(last)}`,
        );
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("priors / sparks keys are valid delta windows", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      if (!l.summary) continue;
      for (const field of ["priors", "sparks"]) {
        const obj = l.summary[field] as Json | undefined;
        if (!obj || typeof obj !== "object") continue;
        for (const k of Object.keys(obj)) {
          if (!DELTA_WINDOWS.has(k)) bad.push(`${l.id}: ${field} has invalid window '${k}'`);
        }
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("each sparks[w] ends at latest; each priors[w] precedes latest", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      if (!l.summary) continue;
      const latest = l.summary.latest as Json | undefined;
      if (!latest) continue;
      const sparks = (l.summary.sparks ?? {}) as Record<string, Json[]>;
      for (const [w, arr] of Object.entries(sparks)) {
        if (!Array.isArray(arr) || arr.length === 0) {
          bad.push(`${l.id}: sparks.${w} empty`);
          continue;
        }
        if (arr[arr.length - 1].t !== latest.t) {
          bad.push(`${l.id}: sparks.${w} ends ${arr[arr.length - 1].t}, not latest ${latest.t}`);
        }
      }
      const priors = (l.summary.priors ?? {}) as Record<string, Json>;
      for (const [w, p] of Object.entries(priors)) {
        if (p && typeof p.t === "string" && p.t >= latest.t) {
          bad.push(`${l.id}: priors.${w} (${p.t}) is not older than latest ${latest.t}`);
        }
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("latestProjection is present iff the data file has projections", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      if (!l.summary) continue;
      const hasProj = !!l.data.projections && Object.keys(l.data.projections).length > 0;
      const hasLatestProj = !!l.summary.latestProjection;
      if (hasProj !== hasLatestProj) {
        bad.push(`${l.id}: data.projections=${hasProj} but summary.latestProjection=${hasLatestProj}`);
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });
});

describe("cross-file consistency", () => {
  it("data file id matches its filename stem", () => {
    const bad: string[] = [];
    for (const l of loaded) {
      const stem = basename(l.dataFile).replace(/\.json$/, "");
      if (typeof l.data.id === "string" && l.data.id !== stem) {
        bad.push(`${l.id}: data.id '${l.data.id}' != file stem '${stem}'`);
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });
});

describe("referential integrity", () => {
  const ids = sourceIds();
  const chartIds = new Set(charts().map((c) => c.id));

  it("every live chart's sources resolve to a source YAML on disk", () => {
    const bad: string[] = [];
    for (const c of charts()) {
      if (!isLiveChart(c)) continue;
      for (const key of ["sources", "rightAxisSources"]) {
        const arr = c.data[key];
        if (!Array.isArray(arr)) continue;
        for (const s of arr) {
          if (typeof s === "string" && !ids.has(s)) {
            bad.push(`chart ${c.id}: ${key} references missing source '${s}'`);
          }
        }
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("every referenced source has a dataFile that exists on disk", () => {
    const bad: string[] = [];
    for (const s of referencedSources()) {
      if (!s.dataFile) {
        bad.push(`source ${s.id}: no dataFile field`);
        continue;
      }
      if (!existsSync(dataPath(s.dataFile))) {
        bad.push(`source ${s.id}: dataFile missing ${s.dataFile}`);
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("every map chart's choropleth data file(s) exist", () => {
    const geoDir: Record<string, string> = {
      state: "acs_state",
      county: "acs_county",
      tract: "acs_tract",
      "block-group": "acs_block_group",
    };
    const bad: string[] = [];
    for (const c of charts()) {
      if (!isLiveChart(c) || c.data.render !== "map") continue;
      const geo = c.data.geo as string;
      const indicator = c.data.indicator as string;
      const vintage = c.data.vintage as string;
      const dir = geoDir[geo];
      if (!dir || !indicator || !vintage) {
        bad.push(`map ${c.id}: missing geo/indicator/vintage`);
        continue;
      }
      const file = `${indicator}_${vintage}.json`;
      if (geo === "tract" || geo === "block-group") {
        const states = Array.isArray(c.data.states)
          ? (c.data.states as string[])
          : c.data.state
            ? [c.data.state as string]
            : [];
        for (const st of states) {
          const p = dataPath(`data/${dir}/${st.toLowerCase()}/${file}`);
          if (!existsSync(p)) bad.push(`map ${c.id}: missing ${dir}/${st.toLowerCase()}/${file}`);
        }
      } else {
        const p = dataPath(`data/${dir}/${file}`);
        if (!existsSync(p)) bad.push(`map ${c.id}: missing ${dir}/${file}`);
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("every dashboard's referenced charts exist", () => {
    const bad: string[] = [];
    for (const d of dashboards()) {
      const refs: string[] = [];
      if (Array.isArray(d.data.charts)) refs.push(...(d.data.charts as string[]));
      if (Array.isArray(d.data.sections)) {
        for (const sec of d.data.sections as Json[]) {
          if (Array.isArray(sec?.charts)) refs.push(...(sec.charts as string[]));
        }
      }
      for (const r of refs) {
        if (typeof r === "string" && !chartIds.has(r)) {
          bad.push(`dashboard ${d.id}: references missing chart '${r}'`);
        }
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });

  it("every deprecated chart's aliasOf points to a real chart", () => {
    const bad: string[] = [];
    for (const c of charts()) {
      const alias = c.data.aliasOf;
      if (typeof alias === "string" && !chartIds.has(alias)) {
        bad.push(`chart ${c.id}: aliasOf '${alias}' does not exist`);
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });
});

describe("choropleth value integrity (referenced maps)", () => {
  // The integrity loader above only sees time-series files; choropleth
  // (geo/values) files were value-unchecked, so a map could render blank or
  // garbage states with zero test resistance. Validate the values maps of
  // the state/county maps here (the common, non-sharded case + the proven
  // blind spot). tract/block-group are sharded into thousands of files —
  // their existence is checked above; deep value scanning is left to the
  // --full audit to keep this gate fast.
  const geoDir: Record<string, string> = { state: "acs_state", county: "acs_county" };
  const GEOID_LEN: Record<string, number> = { state: 2, county: 5 };

  it("every referenced state/county map has finite, non-negative values", () => {
    const bad: string[] = [];
    const seen = new Set<string>();
    for (const c of charts()) {
      if (!isLiveChart(c) || c.data.render !== "map") continue;
      const geo = c.data.geo as string;
      const dir = geoDir[geo];
      if (!dir) continue; // state/county only
      const rel = `data/${dir}/${c.data.indicator}_${c.data.vintage}.json`;
      if (seen.has(rel)) continue; // many charts share one indicator file
      seen.add(rel);
      const fp = dataPath(rel);
      if (!existsSync(fp)) continue; // existence is asserted elsewhere
      const d = readJson(fp) as Json;
      const values = d.values as Record<string, unknown> | undefined;
      const keys = values ? Object.keys(values) : [];
      if (!values || keys.length === 0) {
        bad.push(`${rel}: empty/missing values map`);
        continue;
      }
      const len = GEOID_LEN[geo];
      for (const [geoid, v] of Object.entries(values)) {
        if (!/^\d+$/.test(geoid) || geoid.length !== len) {
          bad.push(`${rel}: malformed GEOID '${geoid}'`);
          break;
        }
        if (typeof v !== "number" || !Number.isFinite(v) || v < 0) {
          bad.push(`${rel}: bad value ${JSON.stringify(v)} for ${geoid}`);
          break;
        }
      }
    }
    expect(bad, show(bad)).toEqual([]);
  });
});
