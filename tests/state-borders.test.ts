/**
 * The thicker state-boundary overlay on county / tract / block-group maps must
 * be PRECOMPUTED, not meshed on the user's CPU per paint (Keller's note). For
 * tract/BG maps the overlay is extracted from a small shared us-states asset,
 * minted at build by scripts/build_us_states_topo.mjs. These tests pin:
 *   1. the asset exists, is states-only, and covers all 50 states + DC;
 *   2. the generator stays faithful to the county file's bundled states layer;
 *   3. the overlay mesh logic yields state borders + the national outline, NOT
 *      every county/tract line (the "class" of the original feature).
 */
import { describe, it, expect } from "vitest";
import * as topojsonClient from "topojson-client";
import fs from "node:fs";
import path from "node:path";

const tj: any = topojsonClient;
const MAPS = path.join(process.cwd(), "public", "maps");
const load = (f: string): any => JSON.parse(fs.readFileSync(path.join(MAPS, f), "utf8"));
const stateOf = (g: any): string => String(g?.id ?? g?.properties?.GEOID ?? "").slice(0, 2);
const arcCount = (m: any): number =>
  m && Array.isArray(m.coordinates) ? m.coordinates.length : -1;

describe("precomputed us-states overlay asset", () => {
  const states = load("us-states-10m.json");
  const fc = tj.feature(states, states.objects.states);

  it("is a valid, states-ONLY TopoJSON with all 50 states + DC", () => {
    expect(states.type).toBe("Topology");
    expect(states.objects.states).toBeTruthy();
    // Guards against pointing the asset at the full county file (~1MB) by mistake.
    expect(states.objects.counties).toBeUndefined();
    expect(fc.features.length).toBe(51);
  });

  it("every feature carries a 2-digit FIPS id + GEOID + NAME (for the FIPS filter)", () => {
    for (const f of fc.features) {
      expect(String(f.id)).toMatch(/^\d{2}$/);
      expect(f.properties?.GEOID).toBeTruthy();
      expect(f.properties?.NAME).toBeTruthy();
    }
  });

  it("matches the county file's bundled states layer (generator is faithful)", () => {
    const county = load("us-counties-2024-10m.json");
    const countyStates = tj.feature(county, county.objects.states);
    const a = fc.features.map((f: any) => String(f.id)).sort();
    const b = countyStates.features.map((f: any) => String(f.id)).sort();
    expect(a).toEqual(b);
  });
});

describe("state-border overlay mesh = borders + outline, not every fine line", () => {
  it("county overlay includes the exterior outline but excludes intra-state county lines", () => {
    const county = load("us-counties-2024-10m.json");
    const obj = county.objects.counties;
    const overlay = tj.mesh(county, obj, (a: any, b: any) => a === b || stateOf(a) !== stateOf(b));
    const interiorOnly = tj.mesh(county, obj, (a: any, b: any) => a !== b && stateOf(a) !== stateOf(b));
    const allBoundaries = tj.mesh(county, obj);
    expect(overlay.type).toBe("MultiLineString");
    // exterior arcs included → more than interior-only state borders
    expect(arcCount(overlay)).toBeGreaterThan(arcCount(interiorOnly));
    // same-state county-county arcs excluded → far fewer than every boundary
    expect(arcCount(overlay)).toBeLessThan(arcCount(allBoundaries));
  });

  it("a single-state tract shard meshes to a valid outline", () => {
    const tract = load("dc-tracts-topo.json");
    const obj = tract.objects.tracts;
    const mesh = tj.mesh(tract, obj, (a: any, b: any) => a === b || stateOf(a) !== stateOf(b));
    expect(mesh.type).toBe("MultiLineString");
    expect(arcCount(mesh)).toBeGreaterThan(0);
  });
});
