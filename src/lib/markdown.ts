/**
 * Safe-subset markdown renderer.
 *
 * Used for: section descriptions in saved dashboards + composed
 * dashboard state, plus the markdown-only section variant.
 *
 * Deliberately a SUBSET, not a CommonMark renderer:
 *
 *   - Headings:       ##, ###, #### (h2/h3/h4 only; h1 reserved for
 *                     the dashboard title)
 *   - Bold:           **text** or __text__
 *   - Italic:         *text* or _text_
 *   - Inline code:    `text`
 *   - Code block:     ```\nblock\n```
 *   - Bullet list:    lines starting with "- "
 *   - Numbered list:  lines starting with "1." (any single integer)
 *   - Link:           [text](https:// | http:// | / | mailto:)
 *   - Paragraph:      everything else, separated by blank lines
 *   - Line break:     trailing two spaces on a line
 *
 * What's intentionally NOT supported:
 *
 *   - Raw HTML pass-through (XSS risk — user input lives in URLs
 *     and Supabase rows; this would let a malicious dashboard
 *     stamp a <script> tag onto anyone who opens it)
 *   - Images (out of scope; charts handle the visualization role)
 *   - Tables (could be added later if there's a clear use case)
 *   - Blockquotes (same — rare in dashboard narrative)
 *   - Nested lists (the renderer is line-based and not hierarchical)
 *
 * URL allow-listing: only http://, https://, /-rooted relative, and
 * mailto: schemes pass. Anything else (javascript:, data:, etc.)
 * silently degrades to a non-link text run. The intent is to keep
 * the renderer XSS-safe under any user input — including saved
 * dashboards shared with strangers.
 */

import { escapeHtml } from "./escape-html";

const ALLOWED_URL_PREFIXES = ["http://", "https://", "/", "mailto:"] as const;

function isAllowedUrl(href: string): boolean {
  const trimmed = href.trim();
  if (trimmed.length === 0) return false;
  return ALLOWED_URL_PREFIXES.some((prefix) => trimmed.startsWith(prefix));
}

/**
 * Apply inline markdown (bold, italic, code, links) to a single line
 * of text. Order matters: code first (so backticks inside don't get
 * treated as emphasis), then links, then bold, then italic.
 *
 * Each replacement escapes its content via escapeHtml before
 * wrapping in tags. The raw text outside any markdown construct
 * gets escaped at the end.
 */
function applyInline(line: string): string {
  // Use unique sentinels so escapeHtml at the end doesn't mangle
  // the HTML tags we're about to emit. Replace constructs with
  // placeholders containing a non-printable separator, then escape
  // the rest, then swap placeholders back to real HTML.
  const SOH = ""; // start-of-heading control char; won't appear in user text
  const segments: string[] = [];
  let cursor = line;

  // 1. Inline code: `...` (no nested backticks).
  cursor = cursor.replace(/`([^`\n]+)`/g, (_, body) => {
    const idx = segments.push(`<code>${escapeHtml(body)}</code>`) - 1;
    return `${SOH}${idx}${SOH}`;
  });

  // 2. Links: [text](url).
  cursor = cursor.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, text, url) => {
    if (!isAllowedUrl(url)) {
      // Disallowed scheme — drop the link wrapper and keep text.
      const idx = segments.push(escapeHtml(text)) - 1;
      return `${SOH}${idx}${SOH}`;
    }
    const safeUrl = escapeHtml(url);
    const safeText = escapeHtml(text);
    // External-link rel attributes when the link goes off-site
    // (anything not starting with "/").
    const external = !url.startsWith("/");
    const rel = external ? ' rel="noopener noreferrer"' : "";
    const target = external ? ' target="_blank"' : "";
    const idx =
      segments.push(`<a href="${safeUrl}"${target}${rel}>${safeText}</a>`) - 1;
    return `${SOH}${idx}${SOH}`;
  });

  // 3. Bold: **text** or __text__. (Run before italic so the same
  //    delimiter chars don't double-match.)
  cursor = cursor.replace(
    /\*\*([^*\n]+)\*\*|__([^_\n]+)__/g,
    (_, a, b) => {
      const body = a ?? b ?? "";
      const idx = segments.push(`<strong>${escapeHtml(body)}</strong>`) - 1;
      return `${SOH}${idx}${SOH}`;
    },
  );

  // 4. Italic: *text* or _text_. Single delimiters.
  cursor = cursor.replace(
    /\*([^*\n]+)\*|_([^_\n]+)_/g,
    (_, a, b) => {
      const body = a ?? b ?? "";
      const idx = segments.push(`<em>${escapeHtml(body)}</em>`) - 1;
      return `${SOH}${idx}${SOH}`;
    },
  );

  // 5. Escape the rest of the line (the markdown constructs are
  // already escaped inside their placeholders).
  let out = escapeHtml(cursor);

  // 6. Swap placeholders back to their rendered HTML. The placeholder
  // pattern is SOH<digits>SOH; SOH is non-printable + can't appear
  // in either user input or escapeHtml output, so this is unambiguous.
  out = out.replace(new RegExp(`${SOH}(\\d+)${SOH}`, "g"), (_, idx) => {
    const n = Number(idx);
    return segments[n] ?? "";
  });
  return out;
}

/**
 * Render a markdown string to HTML. Safe to inject via set:html /
 * innerHTML — every user-controlled fragment is escaped before
 * being wrapped in tags.
 */
export function renderMarkdown(input: string): string {
  if (!input) return "";
  // Normalize line endings, and strip the control-char sentinels the
  // renderer uses internally (U+0001 in applyInline, U+0002 for the
  // synthetic line-break marker in flushParagraph) so a user-typed copy
  // of either can't collide with the placeholder machinery.
  const text = input.replace(/\r\n?/g, "\n").replace(/[]/g, "");
  const lines = text.split("\n");
  const out: string[] = [];

  // Block-level state machine. We scan lines and accumulate runs of
  // the same block type, emitting wrapped HTML on type changes.
  let i = 0;
  let para: string[] = [];

  function flushParagraph(): void {
    if (para.length === 0) return;
    // Join lines within a paragraph with <br/> when each line ends
    // with "  " (two spaces), else with a space. Then run inline on
    // the joined text.
    // Mark hard line-breaks (a line ending in two spaces) with a control
    // sentinel, NOT a literal "<br/>": if we split on a literal "<br/>",
    // a user who TYPED "<br/>" would have it treated as a synthetic break
    // and smuggle a real tag past applyInline's escaping. The sentinel
    // (U+0002) is stripped from user input during normalization, so each
    // part runs through applyInline (which escapes any typed "<br/>" to
    // text) and the parts are then re-joined with the real break tag.
    const BR = "";
    const joined = para
      .map((l, idx) => {
        const hasBr = l.endsWith("  ");
        const stripped = hasBr ? l.slice(0, -2) : l;
        return stripped + (idx < para.length - 1 ? (hasBr ? BR : " ") : "");
      })
      .join("");
    const parts = joined.split(BR);
    const rendered = parts.map((p) => applyInline(p)).join("<br/>");
    out.push(`<p>${rendered}</p>`);
    para = [];
  }

  while (i < lines.length) {
    const line = lines[i];

    // Code block: ```...```
    if (line.trimStart().startsWith("```")) {
      flushParagraph();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      // Skip closing fence (if present — unterminated blocks just
      // render whatever was accumulated).
      if (i < lines.length) i++;
      out.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    // Heading: ## / ### / ####
    const headingMatch = /^(#{2,4})\s+(.+)$/.exec(line);
    if (headingMatch) {
      flushParagraph();
      const level = headingMatch[1].length;
      const body = applyInline(headingMatch[2].trim());
      out.push(`<h${level}>${body}</h${level}>`);
      i++;
      continue;
    }

    // Bullet list. Group consecutive "- " lines into one <ul>.
    if (/^-\s+/.test(line)) {
      flushParagraph();
      const items: string[] = [];
      while (i < lines.length && /^-\s+/.test(lines[i])) {
        items.push(applyInline(lines[i].replace(/^-\s+/, "")));
        i++;
      }
      out.push(`<ul>${items.map((it) => `<li>${it}</li>`).join("")}</ul>`);
      continue;
    }

    // Numbered list. Group consecutive "<n>. " lines.
    if (/^\d+\.\s+/.test(line)) {
      flushParagraph();
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(applyInline(lines[i].replace(/^\d+\.\s+/, "")));
        i++;
      }
      out.push(`<ol>${items.map((it) => `<li>${it}</li>`).join("")}</ol>`);
      continue;
    }

    // Blank line ends the current paragraph.
    if (line.trim() === "") {
      flushParagraph();
      i++;
      continue;
    }

    // Plain paragraph text — accumulate until blank line / block.
    para.push(line);
    i++;
  }
  flushParagraph();
  return out.join("\n");
}
