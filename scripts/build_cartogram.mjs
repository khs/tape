// Build population-weighted CONTIGUOUS cartogram geometry (the smooth
// Gastner-Seguy-More flow-based "diffusion" look) for a US geography level.
//
// Why precompute: the cartogram is weighted by POPULATION (stable), not by the
// metric you color it with — so one distorted geometry per (level, vintage)
// serves every indicator (vote margin, poverty %, …). The metric just colors
// the warped polygons, exactly like a normal choropleth. Output is in PROJECTED
// (planar Albers-USA) coordinates, so the renderer draws it with an identity
// projection (it's already projected), not albers-usa.
//
//   node scripts/build_cartogram.mjs            # all configured levels
//   node scripts/build_cartogram.mjs states     # one level
//
// Pipeline per level: topology -> FeatureCollection -> attach population by id
// -> project to planar -> go-cart makeCartogram(weight="population") -> TopoJSON.
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

// --- per-level config (states now; county/cd extend the same shape) ---------
const LEVELS = {
  states: {
    topo: "us-states-10m.json",
    object: "states",
    out: "us-states-cartogram-pop.json",
    // population for a state feature whose topo id is a 2-digit FIPS
    pop: (id) => {
      const postal = FIPS_TO_POSTAL[id];
      if (!postal) return null;
      const f = path.join(DATA, "acs_state", `population_${postal.toLowerCase()}.json`);
      if (!fs.existsSync(f)) return null;
      const pts = JSON.parse(fs.readFileSync(f, "utf8")).points || [];
      return pts.length ? pts[pts.length - 1].v : null;
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

async function buildLevel(key, GoCart) {
  const cfg = LEVELS[key];
  const topo = JSON.parse(fs.readFileSync(path.join(MAPS, cfg.topo), "utf8"));
  const fc = tc.feature(topo, topo.objects[cfg.object]);

  // Attach population; drop features we can't weight.
  const feats = [];
  let missing = 0;
  for (const f of fc.features) {
    const id = String(f.id ?? f.properties?.GEOID ?? f.properties?.id ?? "");
    const pop = cfg.pop(id);
    if (pop == null || !(pop > 0)) { missing++; continue; }
    feats.push({ ...f, id, properties: { ...(f.properties || {}), id, GEOID: id, population: pop } });
  }
  if (missing) console.log(`  [${key}] ${missing} features dropped (no population)`);

  // Project lon/lat -> planar (Albers-USA, AK/HI insets placed), fit to canvas.
  const proj = geoAlbersUsa().fitSize(SIZE, { type: "FeatureCollection", features: feats });
  const projected = {
    type: "FeatureCollection",
    features: feats.map((f) => ({ type: "Feature", id: f.id, properties: f.properties, geometry: rewindGeom(projectGeom(f.geometry, proj)) })),
  };

  // Flow-based contiguous cartogram, weighted by population.
  const cart = GoCart.makeCartogram(projected, "population");
  // go-cart preserves feature order; re-attach id/props defensively.
  cart.features.forEach((f, i) => {
    f.id = projected.features[i].id;
    f.properties = projected.features[i].properties;
  });

  // Correctness check: distorted area should track population.
  const areas = cart.features.map((f) => geomArea(f.geometry));
  const pops = cart.features.map((f) => f.properties.population);
  const r = pearson(areas, pops);

  // Quantize to shrink the file (planar coords → ~1e4 grid is visually lossless
  // at map scale; cuts the unquantized output several-fold).
  const out = ts.topology({ [cfg.object]: cart }, 1e4);
  const outPath = path.join(MAPS, cfg.out);
  fs.writeFileSync(outPath, JSON.stringify(out));
  const kb = (fs.statSync(outPath).size / 1024).toFixed(0);
  console.log(`  [${key}] ${cart.features.length} features, area~pop r=${r.toFixed(3)}, ${kb}KB -> ${path.relative(ROOT, outPath)}`);
  if (r < 0.9) throw new Error(`[${key}] area~population correlation ${r.toFixed(3)} < 0.9 — cartogram looks wrong`);
}

const want = process.argv.slice(2);
const keys = want.length ? want : Object.keys(LEVELS);
const GoCart = await initGoCart({ locateFile: () => WASM });
for (const k of keys) {
  if (!LEVELS[k]) { console.error(`unknown level: ${k}`); continue; }
  await buildLevel(k, GoCart);
}
console.log("cartogram build complete.");
