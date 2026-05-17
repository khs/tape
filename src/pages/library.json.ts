import type { APIRoute } from "astro";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import { getCollection } from "astro:content";
import { loadSourceData } from "../lib/load-data";
import {
  METRO_TAG,
  metroTagsFor,
  parseMetroSourceId,
} from "../lib/geographic-regions";
import {
  CD_TAG,
  STATE_TAG,
  parseCdSourceId,
  parseStateSourceId,
} from "../lib/congressional-districts";

/**
 * Lightweight CBSA-code → display-name lookup, parsed from the
 * pipelines/_crosswalks/cbsa_metro.csv that drives the metro pipelines.
 * Shipped in the manifest so the composer's "Metro area" chip can label
 * each CBSA without a second fetch. Read once per build.
 */
async function loadMetroLookup(): Promise<Record<string, { shortName: string; name: string }>> {
  // Two candidate paths: the dev-mode path (cwd is the repo root when
  // `astro dev` runs from the project root) and the build-time path
  // derived from import.meta.url (cwd may differ during prerender).
  // Try cwd first because Vite's SSR loader sometimes rewrites
  // import.meta.url into a virtual path that fileURLToPath can't
  // resolve.
  const candidates = [
    resolve(process.cwd(), "pipelines", "_crosswalks", "cbsa_metro.csv"),
  ];
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    candidates.push(
      resolve(here, "..", "..", "pipelines", "_crosswalks", "cbsa_metro.csv"),
    );
  } catch {
    // import.meta.url not file-URL-resolvable (some bundler contexts);
    // the cwd candidate is sufficient.
  }
  const out: Record<string, { shortName: string; name: string }> = {};
  let text: string | null = null;
  for (const p of candidates) {
    try {
      text = await readFile(p, "utf-8");
      break;
    } catch {
      // Try next candidate.
    }
  }
  if (text === null) {
    // Crosswalk missing — composer will hide the chip. Not an error.
    return out;
  }
  const lines = text.split(/\r?\n/);
  if (lines.length < 2) return out;
  const header = lines[0].split(",");
  const codeIdx = header.indexOf("cbsa_code");
  const shortIdx = header.indexOf("short_name");
  const nameIdx = header.indexOf("name");
  if (codeIdx < 0 || shortIdx < 0 || nameIdx < 0) return out;
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    // Cheap CSV split: handle one quoted field. The crosswalk only
    // quotes the `name` column (which contains commas). Other columns
    // are alphanumeric / pipe-separated and don't need a full parser.
    const cells = splitMaybeQuoted(line);
    const code = cells[codeIdx]?.trim();
    if (!code) continue;
    out[code] = {
      shortName: cells[shortIdx]?.trim() ?? code,
      name: cells[nameIdx]?.trim() ?? code,
    };
  }
  return out;
}

function splitMaybeQuoted(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuote = !inQuote;
      continue;
    }
    if (ch === "," && !inQuote) {
      out.push(cur);
      cur = "";
      continue;
    }
    cur += ch;
  }
  out.push(cur);
  return out;
}

/**
 * Chart-library manifest consumed by the composer (/compose/) and the
 * client-side /custom/ renderer. Contains metadata only — no time-series data.
 * Points data is fetched on-demand from public/data/<pipeline>/<id>.json.
 *
 * Shape:
 *   {
 *     charts:  [{ id, title, tags, sources, defaultDelta, normalize, blurb,
 *                deprecated, aliasOf, searchText }],
 *     sources: { [id]: { name, shortName, description, kind, pipeline,
 *                        dataFile, supportedDeltas, unit, formatting,
 *                        emphasis, provenance, firstObservation,
 *                        lastObservation, tags, searchText } }
 *   }
 *
 * Tags are pre-populated by pipelines/backfill_source_tags.py: every
 * source inherits the tags of single-source charts that reference it,
 * plus tags from multi-source charts unless the chart's per-source
 * override in MULTI_SOURCE_OVERRIDES restricts which tags go where.
 */
export const prerender = true;

export const GET: APIRoute = async () => {
  const [chartsCol, sourcesCol, metroLookup] = await Promise.all([
    getCollection("charts"),
    getCollection("sources"),
    loadMetroLookup(),
  ]);

  // Restrict the manifest's metro table to CBSAs that actually have at
  // least one source on disk — keeps the composer's metro dropdown from
  // listing metros the pipelines haven't populated yet.
  const metrosInUse = new Set<string>();

  const sources: Record<string, unknown> = {};
  for (const s of sourcesCol) {
    // Read first / last observation dates from the source's data file at
    // build time so the composer can flag charts whose data doesn't cover
    // a fixed-range request without having to fetch each JSON itself.
    let firstObservation: string | undefined;
    let lastObservation: string | undefined;
    try {
      const data = await loadSourceData(s.data.dataFile);
      if (data.kind === "timeseries" && data.points.length > 0) {
        firstObservation = data.points[0].t;
        lastObservation = data.points[data.points.length - 1].t;
      }
    } catch {
      // Missing data file; leave first/last undefined so callers know.
    }
    // Per-source `searchText`: lowercased haystack the composer's source-
    // picker greps against. Includes name/shortName/description (so a
    // ticker like "XOM" or a pipeline-style ID matches even when typing
    // a common name), the source-id itself, and the tags string (so
    // typing "macro" matches every source tagged macro). Same idea as
    // the chart-level searchText below.
    //
    // Three classes of synthetic tags get injected here (rather than
    // mutating thousands of source YAMLs) so the composer's geo-region
    // chips can filter without each YAML having to declare them:
    //   - CD_TAG ("congressional-district") for usaspending/district_*
    //     and acs_cd/* — surfaced under the "States & districts" chip.
    //   - STATE_TAG ("us-state") for usaspending/state_*, fred/state_*,
    //     bls/state_* — surfaced under the same chip via "Statewide".
    //   - METRO_TAG ("metro") + per-CBSA metro:<cbsa> for the metro
    //     pipelines — surfaced under the "Metro area" chip. metroTagsFor
    //     returns both the umbrella and per-CBSA tag in one call.
    // metrosInUse tracks which CBSAs actually appear in the source
    // universe so the manifest only ships those in the metro lookup.
    const declaredTags = s.data.tags ?? [];
    const synthetics: string[] = [];
    if (parseCdSourceId(s.id)) synthetics.push(CD_TAG);
    if (parseStateSourceId(s.id)) synthetics.push(STATE_TAG);
    const metroExtra = metroTagsFor(s.id);
    if (metroExtra.length > 0) synthetics.push(...metroExtra);
    const parsedMetro = parseMetroSourceId(s.id);
    if (parsedMetro) metrosInUse.add(parsedMetro.cbsa);
    const tagsList =
      synthetics.length > 0
        ? [...new Set([...declaredTags, ...synthetics])].sort()
        : declaredTags;
    const sourceSearchText = [
      s.data.name,
      s.data.shortName,
      s.data.description,
      s.id,
      tagsList.join(" "),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    sources[s.id] = {
      id: s.id,
      name: s.data.name,
      shortName: s.data.shortName,
      description: s.data.description,
      kind: s.data.kind,
      pipeline: s.data.pipeline,
      dataFile: s.data.dataFile,
      supportedDeltas: s.data.supportedDeltas,
      unit: s.data.unit,
      formatting: s.data.formatting,
      emphasis: s.data.emphasis,
      provenance: s.data.provenance,
      firstObservation,
      lastObservation,
      tags: tagsList,
      searchText: sourceSearchText,
      unitClass: s.data.unitClass,
    };
  }

  const charts = chartsCol
    // Hide charts tagged deprecated=true without an alias. Aliased ones still
    // expose the redirect so saved dashboards can resolve transparently.
    .filter((c) => !(c.data.deprecated === true && !c.data.aliasOf))
    // Hide single-source pregenerated charts (sources.length === 1 AND no
    // chart-level op) from the composer's Pregenerated tab. They're pure
    // wrappers around their underlying source — users get the same chart
    // by clicking the source in the Sources tab, which goes through
    // addSourceAsChart and produces an inline single-series chart. Keeping
    // them surfaces redundant cards in the picker.
    //
    // The chart YAMLs stay on disk because the preset dashboard pages
    // (/us-macro/, /stocks/, /tech/, /va-08/) resolve chart IDs via
    // getEntry("charts", id) directly, NOT through this manifest. So the
    // preset pages keep rendering; only the composer's Pregenerated tab
    // is affected. Charts with an `op` set (e.g. 10Y-2Y diff over 2
    // sources) stay visible; multi-source charts always stay visible.
    .filter((c) => {
      const srcCount = (c.data.sources ?? []).length;
      const hasOp = !!(c.data as { op?: string }).op;
      return srcCount > 1 || hasOp;
    })
    .map((c) => {
      // Build a single concatenated `searchText` field on the server to keep
      // client-side search cheap and consistent. Includes title, id, tags,
      // and each linked source's name/shortName/description.
      const sourceText = (c.data.sources ?? [])
        .map((sid) => {
          const s = (sources as Record<string, { name?: string; shortName?: string; description?: string }>)[sid];
          if (!s) return "";
          return [s.name, s.shortName, s.description].filter(Boolean).join(" ");
        })
        .join(" ");
      const searchText = [
        c.data.title,
        c.id,
        (c.data.tags ?? []).join(" "),
        c.data.blurb ?? "",
        sourceText,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return {
        id: c.id,
        title: c.data.title,
        tags: c.data.tags ?? [],
        sources: c.data.sources,
        render: c.data.render,
        defaultDelta: c.data.defaultDelta,
        normalize: c.data.normalize,
        // Carry chart-level `op` so the composer's Pregenerated tab can
        // render op-collapsed charts (10Y-2Y spread, future spread/ratio
        // charts) the same way the published dashboards do, and so
        // promote-library-to-inline preserves the op.
        op: (c.data as { op?: "divide" | "sum" | "diff" }).op,
        seriesLabels: c.data.seriesLabels,
        blurb: c.data.blurb,
        emphasis: c.data.emphasis,
        deprecated: c.data.deprecated,
        aliasOf: c.data.aliasOf,
        searchText,
      };
    });

  // Trim the metro lookup to entries that appear in at least one
  // source. Sorted by short name so the composer dropdown is
  // alphabetical out of the box.
  const metros: Record<string, { shortName: string; name: string }> = {};
  const usedCodes = [...metrosInUse].sort((a, b) => {
    const an = metroLookup[a]?.shortName ?? a;
    const bn = metroLookup[b]?.shortName ?? b;
    return an.localeCompare(bn);
  });
  for (const code of usedCodes) {
    metros[code] = metroLookup[code] ?? { shortName: code, name: code };
  }

  const body = JSON.stringify({ charts, sources, metros, metroTag: METRO_TAG });
  return new Response(body, {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=300",
    },
  });
};
