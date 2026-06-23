/**
 * Fast extractor for the THREE flat top-level fields the data audit's
 * all-source passes need from each of the ~36k source YAMLs: `dataFile`,
 * `kind`, `tags`. Full `js-yaml` parsing every source just to read those three
 * is the bulk of audit-source-data.mjs's runtime (it builds a complete AST +
 * object graph per file, which pages hard under memory pressure on a 16GB box).
 *
 * A line-scan over the uniform, generator-emitted shape is ~10x lighter. It is
 * deliberately CONSERVATIVE: it understands only simple `key: value` scalars and
 * the two `tags` list forms (block `- x` / inline `[a, b]`). If a file doesn't
 * yield both `dataFile` and `kind` as plain scalars, scanSourceFields returns
 * null so the caller falls back to the real parser — so anything unusual
 * (quoted oddly, anchors, multi-doc, folded scalars) is still parsed correctly,
 * just not on the fast path. Verified output-identical to js-yaml across the
 * whole corpus (35,896 files, 0 mismatches) before shipping; unit-tested in
 * tests/scan-source-fields.test.ts.
 *
 * Scope note: this reads ONLY dataFile/kind/tags. It is NOT a YAML parser and
 * must not be reused anywhere that needs other fields or real validation —
 * Astro's content layer + the audit's referenced-source pass remain the real
 * gates.
 */

function stripQuotes(s) {
  const t = s.trim();
  if (t.length >= 2 &&
      ((t[0] === '"' && t[t.length - 1] === '"') ||
       (t[0] === "'" && t[t.length - 1] === "'"))) {
    return t.slice(1, -1);
  }
  return t;
}

/**
 * @param {string} text raw YAML file contents
 * @returns {{dataFile: string, kind: string, tags: string[]} | null}
 *   null = "not the uniform shape, fall back to js-yaml".
 */
export function scanSourceFields(text) {
  const lines = text.split(/\r?\n/);
  let dataFile;
  let kind;
  let tags;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;
    // Only column-0 keys: every nested field (formatting:, provenance:) is
    // indented, so `^key:` can't collide with them.
    if ((m = /^dataFile:[ \t]*(.+?)[ \t]*$/.exec(line))) {
      dataFile = stripQuotes(m[1]);
    } else if ((m = /^kind:[ \t]*(.+?)[ \t]*$/.exec(line))) {
      kind = stripQuotes(m[1]);
    } else if (/^tags:[ \t]*$/.test(line)) {
      // Block list: consume following `- item` lines at any indent until the
      // next column-0 key (or a non-list, non-blank, non-comment line).
      tags = [];
      for (let j = i + 1; j < lines.length; j++) {
        const item = /^[ \t]*-[ \t]+(.+?)[ \t]*$/.exec(lines[j]);
        if (item) { tags.push(stripQuotes(item[1])); continue; }
        if (/^[ \t]*$/.test(lines[j]) || /^[ \t]*#/.test(lines[j])) continue;
        break;
      }
    } else if ((m = /^tags:[ \t]*\[(.*)\][ \t]*$/.exec(line))) {
      // Inline list: tags: [a, b]
      tags = m[1]
        .split(",")
        .map((s) => stripQuotes(s.trim()))
        .filter((s) => s.length > 0);
    }
  }
  // Schema requires both dataFile + kind. If the fast scan didn't see them as
  // plain scalars, the file is non-uniform — signal a fallback.
  if (typeof dataFile !== "string" || typeof kind !== "string") return null;
  return { dataFile, kind, tags: tags ?? [] };
}
