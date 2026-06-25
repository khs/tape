// Mint a small standalone states-only TopoJSON from the bundled county file.
//
// Why: ChartMap draws a thicker STATE-boundary overlay on county / tract /
// block-group choropleths. County/state boundary files already ship a `states`
// layer, but the per-state tract / block-group files do not — so without this
// asset the tract/BG overlay would have to mesh the shard on the client. This
// produces one tiny, shared, cacheable states file the client extracts from
// instead (zero client-side meshing anywhere).
//
// How: us-counties-2024-10m.json is a quantized TopoJSON whose `states` object
// references a SUBSET of the shared `arcs`. We keep only `objects.states`, prune
// `arcs` to the arcs those geometries reference, and re-index. The quantization
// `transform` is preserved verbatim, so coordinates are unchanged.
//
// Static derived asset (state boundaries don't change between Census vintages):
// run once and commit public/maps/us-states-10m.json; no refresh-workflow step.
//
//   node scripts/build_us_states_topo.mjs

import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

// Named nodeRequire (not `require`) so TS doesn't read the call as the ambient
// CommonJS import form and flag the local as unused (ts 6133).
const nodeRequire = createRequire(import.meta.url);
const tc = nodeRequire("topojson-client");

const ROOT = process.cwd();
const SRC = path.join(ROOT, "public", "maps", "us-counties-2024-10m.json");
const OUT = path.join(ROOT, "public", "maps", "us-states-10m.json");

const county = JSON.parse(fs.readFileSync(SRC, "utf8"));
const states = county.objects.states;
if (!states) throw new Error(`no 'states' object in ${SRC}`);

// Collect every arc index referenced by the states geometries. A leaf index i
// references arcs[i]; a negative index references arcs[~i] reversed.
const used = new Set();
const collect = (arcs) => {
  if (typeof arcs === "number") {
    used.add(arcs < 0 ? ~arcs : arcs);
    return;
  }
  for (const a of arcs) collect(a);
};
for (const g of states.geometries) if (g.arcs) collect(g.arcs);

const usedSorted = [...used].sort((a, b) => a - b);
const remap = new Map(usedSorted.map((oldIdx, newIdx) => [oldIdx, newIdx]));
const newArcs = usedSorted.map((i) => county.arcs[i]);

// Rewrite arc references to the pruned, re-indexed arcs (sign preserved).
const remapArcs = (arcs) => {
  if (typeof arcs === "number") {
    const old = arcs < 0 ? ~arcs : arcs;
    const ni = remap.get(old);
    return arcs < 0 ? ~ni : ni;
  }
  return arcs.map(remapArcs);
};
const newGeometries = states.geometries.map((g) =>
  g.arcs ? { ...g, arcs: remapArcs(g.arcs) } : g,
);

const out = {
  type: "Topology",
  transform: county.transform,
  objects: { states: { ...states, geometries: newGeometries } },
  arcs: newArcs,
};

fs.writeFileSync(OUT, JSON.stringify(out));

// Sanity-check: the pruned file must yield the same state features as the source.
const before = tc.feature(county, county.objects.states).features.length;
const after = tc.feature(out, out.objects.states).features.length;
const srcBytes = fs.statSync(SRC).size;
const outBytes = fs.statSync(OUT).size;
console.log(`states features: ${before} (source) -> ${after} (pruned)`);
console.log(`arcs: ${county.arcs.length} -> ${newArcs.length}`);
console.log(`bytes: ${(srcBytes / 1024).toFixed(0)}KB (county) -> ${(outBytes / 1024).toFixed(0)}KB (states-only)`);
if (after !== before) throw new Error("feature count changed — prune is wrong");
console.log(`wrote ${path.relative(ROOT, OUT)}`);
