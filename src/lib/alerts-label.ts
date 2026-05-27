/**
 * Default-label composer for alert rules.
 *
 * Builds a sensible auto-label from (source name, condition, threshold)
 * so the user doesn't have to type one for the common case. Example
 * inputs / outputs:
 *
 *   { sourceName: "CPI year-over-year (US, all urban consumers)",
 *     condition: "gt", thresholdRaw: "4",
 *     formatting: { style: "percent", decimals: 1 } }
 *     → "CPI year-over-year (US, all urban consumers) > 4.0%"
 *
 *   { sourceName: "10-year Treasury yield",
 *     condition: "gte", thresholdRaw: "5",
 *     formatting: { style: "percent", decimals: 2 } }
 *     → "10-year Treasury yield ≥ 5.00%"
 *
 *   { sourceName: "VIX", condition: "gte", thresholdRaw: "30" }
 *     → "VIX ≥ 30"  (no formatting → bare number)
 *
 *   { sourceName: "XOM market cap", condition: "lt",
 *     thresholdRaw: "400",
 *     formatting: { style: "currency", decimals: 0, notation: "compact",
 *                   scaleFactor: 1e9 } }
 *     → "XOM market cap < $400B"  (formatValue handles compact suffix)
 *
 * Pure: no DOM access, no I/O. Easy to lock down in tests so a copy
 * change here is visible in CI rather than silently shipped.
 *
 * Why not just hardcode "{name} {op} {threshold}{unit}" in alerts.astro:
 * the unit logic (percent → "%", currency → "$" prefix, bps → " bps",
 * scaleFactor + compact-notation for billions / trillions) is already
 * solved by formatValue. Composing here keeps the auto-label in lockstep
 * with the rest of the site's value rendering — if formatValue gets a
 * new style (e.g. "ratio"), this composer inherits the right format for
 * free.
 */
import type { Formatting } from "./format";
import { formatValue } from "./format";

/** Condition values the /alerts/ page select uses. Mirrors the
 *  `<option value="…">` set in alerts.astro's condition dropdown.
 *  Kept as a string union to make the switch in composeDefaultLabel
 *  exhaustive — a new condition added to the form must be wired
 *  here too or the compiler complains. */
export type AlertCondition =
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "crosses_above"
  | "crosses_below"
  | "change_above";

/**
 * Human-readable text fragment for the condition. Math symbols for
 * the four simple comparisons (so the label stays compact), words
 * for the cross / change ops where the symbol would be ambiguous.
 */
export function conditionPhrase(condition: AlertCondition): string {
  switch (condition) {
    case "gt":
      return ">";
    case "gte":
      // U+2265 GREATER-THAN OR EQUAL TO — matches the symbol in the
      // condition dropdown's option text.
      return "≥";
    case "lt":
      return "<";
    case "lte":
      return "≤";
    case "crosses_above":
      return "crosses above";
    case "crosses_below":
      return "crosses below";
    case "change_above":
      return "changes by more than";
  }
}

export interface ComposeDefaultLabelInput {
  /** Display name of the source (typically `source.name` from
   *  library.json). For derived rules pass the composed "A ÷ B"
   *  label. Required — returns "" if missing. */
  sourceName: string;
  /** Selected condition. Required. */
  condition: AlertCondition;
  /** Raw string from the threshold input. Empty / non-numeric →
   *  returns "" (incomplete form, no label yet). */
  thresholdRaw: string;
  /** Source's formatting, if known. When present the threshold is
   *  rendered with formatValue so units (%, $, bps, compact-T/B/M
   *  suffixes) appear correctly. When absent the threshold renders
   *  as a bare number. */
  formatting?: Formatting;
}

/**
 * Compose the default label. Returns "" when any required piece is
 * missing (the caller can use that to decide whether to populate the
 * field or leave it empty).
 */
export function composeDefaultLabel(input: ComposeDefaultLabelInput): string {
  const name = input.sourceName.trim();
  const raw = input.thresholdRaw.trim();
  if (!name || !raw) return "";
  const n = Number(raw);
  if (!Number.isFinite(n)) return "";
  const thresholdText = input.formatting
    ? formatValue(n, input.formatting)
    : raw;
  const phrase = conditionPhrase(input.condition);
  return `${name} ${phrase} ${thresholdText}`;
}
