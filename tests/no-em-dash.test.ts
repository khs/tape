/**
 * Em-dash guard for authored prose.
 *
 * House style: no em-dashes (—, U+2014) in user-facing copy — they read as an
 * AI tell. Structured name separators ("GDP — California") are the documented
 * exception: they live in source/chart YAML `name:` / `shortName:` fields (and
 * the equivalent structured-label fields), NOT in prose.
 *
 * Two suites:
 *   1. Dashboard .mdx files are pure authored prose (intro + section blurbs),
 *      so ANY em-dash in one is a violation.
 *   2. Source YAMLs carry both: a `description:` / `blurb:` is PROSE (banned),
 *      while a `name:` / `shortName:` separator is the exempt structured form.
 *      So we scan the corpus but flag em-dashes ONLY in the prose fields.
 *
 * The YAML scan is line-oriented rather than a full js-yaml parse: it stays
 * fast across the ~38k source files and, by tracking which top-level key each
 * physical line belongs to, it correctly (a) follows a folded/multi-line
 * `description:` value onto its continuation lines and (b) exempts `name:` /
 * `shortName:` and nested structured labels (provenance.provider, etc.) whose
 * top-level key is never `description`/`blurb`.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ROOT } from "./corpus";

function filesWithExt(dir: string, ext: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...filesWithExt(p, ext));
    else if (e.name.endsWith(ext)) out.push(p);
  }
  return out;
}

/** Top-level YAML keys whose values are user-facing PROSE (em-dash banned). */
const PROSE_KEYS = new Set(["description", "blurb"]);

/** A physical line that opens a top-level key (no leading whitespace). */
const TOP_LEVEL_KEY = /^([A-Za-z][\w-]*):/;

describe("no em-dashes in authored prose", () => {
  it("dashboard .mdx files contain no em-dash (—)", () => {
    const offenders: string[] = [];
    for (const fp of filesWithExt(join(ROOT, "src", "content"), ".mdx")) {
      const lines = readFileSync(fp, "utf-8").split("\n");
      lines.forEach((line, i) => {
        if (line.includes("—")) {
          const rel = fp.slice(ROOT.length + 1).replace(/\\/g, "/");
          offenders.push(`${rel}:${i + 1}: ${line.trim().slice(0, 80)}`);
        }
      });
    }
    expect(
      offenders,
      `\nEm-dash (—) found in authored prose. Use a comma, parens, or rephrase ` +
        `(house style: em-dashes read as an AI tell):\n  ${offenders.join("\n  ")}\n`,
    ).toEqual([]);
  });

  it("source YAML description/blurb prose contains no em-dash (—)", async () => {
    const offenders: string[] = [];
    const sourcesDir = join(ROOT, "src", "content", "sources");
    const files = filesWithExt(sourcesDir, ".yaml");
    // Reads ~38k source YAMLs (most contain an em-dash in an exempt name: field,
    // so the fast-reject rarely fires -> nearly the whole corpus is read). Read
    // ASYNC in bounded batches, not a synchronous readFileSync loop: sync opens
    // block the worker and, under the full parallel suite on Windows, 38k opens
    // blew past even a 60s timeout. Batched async reads overlap the I/O and yield
    // to the event loop, keeping this ~1-2s.
    const scan = (fp: string, text: string): void => {
      if (!text.includes("—")) return; // fast reject: no em-dash anywhere
      // Track which top-level key each physical line belongs to. A folded /
      // multi-line description keeps its continuation lines (indented, so they
      // DON'T open a new top-level key) attributed to `description`; a `name:` /
      // `shortName:` line opens its own key and so is exempt.
      let currentKey: string | null = null;
      text.split("\n").forEach((line, i) => {
        const m = line.match(TOP_LEVEL_KEY);
        if (m) currentKey = m[1];
        if (currentKey && PROSE_KEYS.has(currentKey) && line.includes("—")) {
          const rel = fp.slice(ROOT.length + 1).replace(/\\/g, "/");
          offenders.push(`${rel}:${i + 1}: ${line.trim().slice(0, 80)}`);
        }
      });
    };
    const BATCH = 256; // well under the open-file-descriptor ceiling
    for (let i = 0; i < files.length; i += BATCH) {
      const chunk = files.slice(i, i + BATCH);
      const texts = await Promise.all(chunk.map((fp) => readFile(fp, "utf-8")));
      texts.forEach((text, j) => scan(chunk[j], text));
    }
    expect(
      offenders,
      `\nEm-dash (—) found in a source YAML description/blurb (prose). Replace ` +
        `with a comma, colon, or parens (name:/shortName: separators are exempt; ` +
        `only prose fields are checked):\n  ${offenders.join("\n  ")}\n`,
    ).toEqual([]);
    // Generous ceiling (~2s on Linux CI): under the local Windows parallel suite
    // this 38k-file walk is starved for I/O until the other 54 files finish, so
    // it must outlast the whole suite's wall time, not its own compute time.
  }, 120000);
});
