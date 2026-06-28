// Build population-weighted CONTIGUOUS cartogram geometry (the smooth
// Gastner-Seguy-More flow-based "diffusion" look) for US geography levels.
//
// Why precompute: the cartogram is weighted by POPULATION, not the metric you
// color it with — so one distorted geometry per (level, population-vintage)
// serves every indicator (vote margin, poverty %, …). The metric just colors the
// warped polygons, exactly like a normal choropleth. Output is PROJECTED (planar
// Albers-USA) coords, so the renderer draws it with an identity projection.
//
// STATE level is VINTAGED: one cartogram per presidential-election year
// 1976-2024, weighted by that year's population (FRED <ST>POP, Census estimates,
// annual back to 1970). The renderer snaps a map's displayed vintage to the
// nearest one, so the election year-slider is weighted by the population of THAT
// era, not today's. CD level is single/latest — the 118th districts didn't exist
// before 2022, so there's nothing to vintage-match against (and they're ~equal
// population anyway).
//
//   node scripts/build_cartogram.mjs            # states (vintaged) + cd
//   node scripts/build_cartogram.mjs states     # just the state vintages
//   node scripts/build_cartogram.mjs cd         # just cd
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { geoAlbersUsa } from "d3-geo";

const nodeRequire = createRequire(import.meta.url);
const initGoCart = nodeRequire("go-cart-wasm");
const tc = nodeRequire("topojson-client");
const ts = nodeRequire("topojson-server");

const ROOT = process.cwd();
const MAPS = path.join(ROOT, "public", "maps");
const DATA = path.join(ROOT, "public", "data");
const WASM = path.join(ROOT, "node_modules", "go-cart-wasm", "dist", "cart.wasm");
const SIZE = [975, 610]; // standard d3 us-atlas canvas; cartogram is scale-free

// Presidential election years — the vintages we emit state cartograms for. Maps
// snap to the nearest; population changes slowly so 4-year steps are visually
// lossless, and the election year-slider lands on exact matches.
const STATE_VINTAGES = [];
for (let y = 1976; y <= 2024; y += 4) STATE_VINTAGES.push(y);

// FIPS -> USPS postal (50 + DC). Mirror of src/lib/state-fips.ts (a .mjs build
// script can't import the .ts); territories omitted (no state topo/pop).
const FIPS_TO_POSTAL = {
  "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
  "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
  "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
  "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
  "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
  "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
  "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
  "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
  "54": "WV", "55": "WI", "56": "WY",
};

// Latest value from a timeseries JSON ({points:[{t,v}]}), or null if absent.
function lastV(file) {
  if (!fs.existsSync(file)) return null;
  const pts = JSON.parse(fs.readFileSync(file, "utf8")).points || [];
  return pts.length ? pts[pts.length - 1].v : null;
}

// --- single-file levels (cd; county would extend the same shape) ------------
const LEVELS = {
  cd: {
    topo: "us-cd118-10m.json",
    object: "cd",
    out: "us-cd-cartogram-pop.json",
    // Partial cartogram: districts are drawn to ~equal population, so a FULL
    // equalization (strength 1) over-warps them for no analytic gain — every
    // district already holds the same number of people. Blend halfway toward the
    // cartogram so shapes stay recognizable while still shedding land-area bias.
    strength: 0.5,
    // CD topo id = 2-digit state FIPS + 2-digit district ("0804" = CO-04).
    pop: (id) => {
      const postal = FIPS_TO_POSTAL[id.slice(0, 2)];
      if (!postal) return null; // island territories (GU/AS/MP/VI/PR) → dropped
      const lo = postal.toLowerCase();
      // Normal multi-district CD.
      const cdv = lastV(path.join(DATA, "acs_cd", `population_${lo}_${id.slice(2)}.json`));
      if (cdv != null) return cdv;
      // At-large state (topo "XX00") or DC delegate ("1198"): the district IS the
      // whole state and acs_cd emits no file, so use the state population.
      return lastV(path.join(DATA, "acs_state", `population_${lo}.json`));
    },
  },
};

// Project every coordinate of a Polygon/MultiPolygon through `proj`.
function projectGeom(geom, proj) {
  const ring = (r) => r.map((p) => proj(p)).filter((p) => p && isFinite(p[0]) && isFinite(p[1]));
  if (geom.type === "Polygon") return { type: "Polygon", coordinates: geom.coordinates.map(ring) };
  if (geom.type === "MultiPolygon")
    return { type: "MultiPolygon", coordinates: geom.coordinates.map((poly) => poly.map(ring)) };
  return geom;
}

// go-cart reads ring winding to tell exterior rings from holes; d3/topojson
// polygons (after projection) carry the opposite winding, so go-cart sees every
// ring as a hole ("n_polyinreg == n_holes"). Rewind to RFC 7946: exterior ring
// CCW (positive signed area), holes CW.
function signedArea(r) {
  let a = 0;
  for (let i = 0; i < r.length - 1; i++) a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
  return a / 2;
}
function rewindRings(rings) {
  return rings.map((r, i) => {
    // geoAlbersUsa outputs screen coords (y down), which flips the signed-area
    // sign vs math convention: an RFC-7946 exterior ring (geographically CCW)
    // has NEGATIVE signed area here, holes positive. go-cart wants that.
    const wantPositive = i !== 0; // exterior negative (screen), holes positive
    return signedArea(r) > 0 === wantPositive ? r : r.slice().reverse();
  });
}
function rewindGeom(geom) {
  if (geom.type === "Polygon") return { type: "Polygon", coordinates: rewindRings(geom.coordinates) };
  if (geom.type === "MultiPolygon")
    return { type: "MultiPolygon", coordinates: geom.coordinates.map(rewindRings) };
  return geom;
}

// Partial cartogram: move each output vertex back toward its original (projected)
// position by (1 - t). t=1 is the full area∝population cartogram; t<1 keeps shapes
// more recognizable. go-cart displaces existing vertices without densifying, so
// in/out geometries share vertex structure 1:1 (verified) and we can lerp pairwise.
function lerpToward(outG, inG, t) {
  const lr = (oR, iR) => {
    for (let i = 0; i < oR.length; i++) {
      oR[i][0] = iR[i][0] + t * (oR[i][0] - iR[i][0]);
      oR[i][1] = iR[i][1] + t * (oR[i][1] - iR[i][1]);
    }
  };
  if (outG.type === "Polygon") outG.coordinates.forEach((r, ri) => lr(r, inG.coordinates[ri]));
  else if (outG.type === "MultiPolygon")
    outG.coordinates.forEach((po, pi) => po.forEach((r, ri) => lr(r, inG.coordinates[pi][ri])));
}

function ringArea(r) {
  let a = 0;
  for (let i = 0; i < r.length - 1; i++) a += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1];
  return Math.abs(a / 2);
}
function geomArea(g) {
  if (!g) return 0;
  if (g.type === "Polygon") return g.coordinates.reduce((s, r, i) => s + (i === 0 ? ringArea(r) : -ringArea(r)), 0);
  if (g.type === "MultiPolygon")
    return g.coordinates.reduce((s, poly) => s + poly.reduce((ps, r, i) => ps + (i === 0 ? ringArea(r) : -ringArea(r)), 0), 0);
  return 0;
}
// Pearson correlation — the cartogram is correct iff post-distortion AREA
// tracks POPULATION across units.
function pearson(xs, ys) {
  const n = xs.length, mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  return sxy / Math.sqrt(sxx * syy);
}

// Core: features (lon/lat, properties.population) -> quantized cartogram TopoJSON.
function buildCartogram(feats, objectName, outName, strength, label, GoCart) {
  // Project lon/lat -> planar (Albers-USA, AK/HI insets placed), fit to canvas.
  const proj = geoAlbersUsa().fitSize(SIZE, { type: "FeatureCollection", features: feats });
  const projected = {
    type: "FeatureCollection",
    features: feats.map((f) => ({ type: "Feature", id: f.id, properties: f.properties, geometry: rewindGeom(projectGeom(f.geometry, proj)) })),
  };

  // Flow-based contiguous cartogram, weighted by population.
  const cart = GoCart.makeCartogram(projected, "population");
  cart.features.forEach((f, i) => {
    f.id = projected.features[i].id;
    f.properties = projected.features[i].properties;
  });

  // Validate the FULL go-cart output (area must track population) BEFORE any
  // softening or writing, so a degenerate run leaves no corrupt artifact. NaN-safe:
  // a broken winding gives zero area variance → r = NaN, and `NaN < x` is false,
  // so use !(r >= 0.9) to trip on NaN too. (Check the full output, not the blend:
  // a partial blend deliberately breaks area∝pop, and the blend is a convex combo
  // of two valid same-winding polygons so it can't add the degeneracy this catches.)
  const areas = cart.features.map((f) => geomArea(f.geometry));
  const pops = cart.features.map((f) => f.properties.population);
  const r = pearson(areas, pops);
  if (!(r >= 0.9)) {
    const shown = Number.isFinite(r) ? r.toFixed(3) : "NaN";
    throw new Error(`[${label}] area~population correlation ${shown} < 0.9 — cartogram looks wrong (check ring winding)`);
  }

  if (strength < 1) {
    for (let k = 0; k < cart.features.length; k++) {
      lerpToward(cart.features[k].geometry, projected.features[k].geometry, strength);
    }
  }
  // Quantize to shrink the file (planar coords → ~1e4 grid is visually lossless
  // at map scale; cuts the unquantized output several-fold).
  const out = ts.topology({ [objectName]: cart }, 1e4);
  const outPath = path.join(MAPS, outName);
  fs.writeFileSync(outPath, JSON.stringify(out));
  const kb = (fs.statSync(outPath).size / 1024).toFixed(0);
  console.log(`  [${label}] ${cart.features.length} features, full r=${r.toFixed(3)}, strength=${strength}, ${kb}KB -> ${outName}`);
  return outPath;
}

// Single-file level (cd): read topo, attach latest population, build one file.
function buildLevel(key, GoCart) {
  const cfg = LEVELS[key];
  const topo = JSON.parse(fs.readFileSync(path.join(MAPS, cfg.topo), "utf8"));
  const fc = tc.feature(topo, topo.objects[cfg.object]);
  const feats = [];
  let missing = 0;
  for (const f of fc.features) {
    const id = String(f.id ?? f.properties?.GEOID ?? f.properties?.id ?? "");
    const pop = cfg.pop(id);
    if (pop == null || !(pop > 0)) { missing++; continue; }
    feats.push({ ...f, id, properties: { ...(f.properties || {}), id, GEOID: id, population: pop } });
  }
  if (missing) console.log(`  [${key}] ${missing} features dropped (no population)`);
  buildCartogram(feats, cfg.object, cfg.out, cfg.strength ?? 1, key, GoCart);
}

// Annual state population (thousands) per election-year vintage, from FRED's
// <ST>POP series (Census resident-population estimates, keyless fredgraph.csv —
// the only FRED access this project uses). Returns { year -> { fips -> pop } }.
async function fetchStatePopByYear() {
  const byYear = {};
  for (const y of STATE_VINTAGES) byYear[y] = {};
  for (const [fips, postal] of Object.entries(FIPS_TO_POSTAL)) {
    const id = `${postal}POP`;
    const url = `https://fred.stlouisfed.org/graph/fredgraph.csv?id=${id}&cosd=1976-01-01`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`FRED ${id} HTTP ${res.status}`);
    const csv = await res.text();
    for (const line of csv.split(/\r?\n/).slice(1)) {
      const [date, val] = line.split(",");
      if (!date || val == null || val === "." || val.trim() === "") continue;
      const yr = parseInt(date.slice(0, 4), 10);
      if (byYear[yr]) byYear[yr][fips] = parseFloat(val);
    }
  }
  return byYear;
}

// State level: one cartogram per election-year vintage, plus an un-suffixed copy
// of the latest as the default (the renderer falls back to it when a map has no
// vintage to match).
async function buildStatesVintaged(GoCart) {
  const topo = JSON.parse(fs.readFileSync(path.join(MAPS, "us-states-10m.json"), "utf8"));
  const fc = tc.feature(topo, topo.objects.states);
  console.log(`  [states] fetching FRED state population for ${STATE_VINTAGES.length} vintages…`);
  const byYear = await fetchStatePopByYear();
  let latestPath = null;
  for (const y of STATE_VINTAGES) {
    const popMap = byYear[y];
    const feats = [];
    for (const f of fc.features) {
      const id = String(f.id);
      const pop = popMap[id];
      if (pop == null || !(pop > 0)) continue;
      feats.push({ ...f, id, properties: { id, GEOID: id, population: pop } });
    }
    if (feats.length < 50) throw new Error(`[states@${y}] only ${feats.length} states have population — FRED fetch incomplete`);
    latestPath = buildCartogram(feats, "states", `us-states-cartogram-pop-${y}.json`, 1, `states@${y}`, GoCart);
  }
  // Default (un-suffixed) = latest vintage, for the non-vintage render path.
  if (latestPath) fs.copyFileSync(latestPath, path.join(MAPS, "us-states-cartogram-pop.json"));
  // Manifest of available vintages so the renderer can snap a map's displayed
  // vintage to the nearest cartogram without hardcoding the year list.
  fs.writeFileSync(
    path.join(MAPS, "us-states-cartogram-vintages.json"),
    JSON.stringify(STATE_VINTAGES),
  );
}

const want = process.argv.slice(2);
const doStates = !want.length || want.includes("states");
const doCd = !want.length || want.includes("cd");
const GoCart = await initGoCart({ locateFile: () => WASM });
if (doStates) await buildStatesVintaged(GoCart);
if (doCd) buildLevel("cd", GoCart);
console.log("cartogram build complete.");
