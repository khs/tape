/**
 * Em-dash guard for authored prose.
 *
 * House style: no em-dashes (—, U+2014) in user-facing copy — they read as an
 * AI tell. Structured name separators ("GDP — California") are the documented
 * exception, but those live in source/chart YAML `name:` fields, not here. The
 * dashboard .mdx files are pure authored prose (intro + section blurbs), so any
 * em-dash in one is the thing we want to catch before it ships.
 *
 * Scope is deliberately narrow (src/content/**\/*.mdx) to stay false-positive-
 * free: it avoids .astro files, whose JSX/JS comments legitimately contain
 * em-dashes, and the YAML corpus, whose `name:` separators are exempt. Widen
 * only with comment-aware scanning.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { ROOT } from "./corpus";

function mdxFiles(dir: string): string[] {
  const out: string[] = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) out.push(...mdxFiles(p));
    else if (e.name.endsWith(".mdx")) out.push(p);
  }
  return out;
}

describe("no em-dashes in authored prose", () => {
  it("dashboard .mdx files contain no em-dash (—)", () => {
    const offenders: string[] = [];
    for (const fp of mdxFiles(join(ROOT, "src", "content"))) {
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
});
