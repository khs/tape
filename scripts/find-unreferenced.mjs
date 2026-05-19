import { readFileSync, readdirSync } from "node:fs";
import { join, relative } from "node:path";

const root = "src/content";
const sourcesDir = `${root}/sources`;
const chartsDir = `${root}/charts`;

function walk(dir, base) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(p, base));
    else if (entry.name.endsWith(".yaml")) {
      const rel = relative(base, p).replaceAll("\\", "/").replace(/\.yaml$/, "");
      out.push(rel);
    }
  }
  return out;
}

const sources = walk(sourcesDir, sourcesDir);
const charts = walk(chartsDir, chartsDir);
console.log(`Total sources: ${sources.length}, charts: ${charts.length}`);

const referenced = new Set();
for (const chart of charts) {
  const yaml = readFileSync(`${chartsDir}/${chart}.yaml`, "utf8");
  const matches = yaml.match(/- ["']?([a-z][a-z_\-0-9]*\/[a-z][a-z_0-9\-]+)["']?/gi) || [];
  for (const m of matches) {
    const s = m.replace(/^-\s*["']?/, "").replace(/["']?$/, "");
    referenced.add(s);
  }
}
console.log(`Sources referenced by some chart: ${referenced.size}`);

const unreferenced = sources.filter((s) => !referenced.has(s));
const byPipe = {};
for (const s of unreferenced) {
  const pipe = s.split("/")[0];
  byPipe[pipe] = (byPipe[pipe] || 0) + 1;
}
console.log("Unreferenced count by pipeline:");
for (const [k, v] of Object.entries(byPipe).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${k}: ${v}`);
}
