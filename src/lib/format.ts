export interface Formatting {
  style: "currency" | "percent" | "number" | "index" | "bps";
  decimals: number;
  currency?: string;
  prefix?: string;
  suffix?: string;
  notation?: "standard" | "compact";
  /**
   * Multiplier applied to the raw value before formatting. Lets a series
   * stored in billions render as raw dollars (`scaleFactor: 1e9`) so
   * notation: "compact" can produce "$1.63T" instead of "$1.63K". Defaults
   * to 1 (no scaling) so existing sources are unaffected.
   *
   * Why not just store raw dollars: the system invariant (see
   * pipelines/rescale_currency_to_billions.py) keeps currency series in
   * billions so derived-source math (X/Y where one is dollars and the
   * other is millions of people) doesn't overflow the float ranges
   * Intl.NumberFormat handles cleanly. scaleFactor is a display-only
   * adapter that lets compact notation render trillions the right way.
   */
  scaleFactor?: number;
}

/**
 * For compact-notation values ("$3.41T", "$456B", "$45.6B") this picks how
 * many digits to show after the decimal so the *displayed* number always
 * carries ~3 significant figures. A market cap of $456B is clearer at
 * "$456B" than "$456.78B"; a $2.34T cap reads as "$2.34T" rather than the
 * truncated "$2T". Rule: 3 leading digits → 0 decimals, 2 → 1, 1 → 2.
 *
 * Non-compact formatting (percent, raw currency, etc.) is unaffected —
 * those still honor fmt.decimals verbatim.
 */
function compactDecimalsFor(v: number): number {
  const absV = Math.abs(v);
  if (!Number.isFinite(absV) || absV < 1) return 2;
  // Largest band ≤ absV. 1e12 = T, 1e9 = B, 1e6 = M, 1e3 = K, 1 = none.
  // Intl's compact suffix picks the same band, so the leading-digit count
  // we compute matches what the rendered string will show.
  const bands = [1e12, 1e9, 1e6, 1e3, 1];
  let band = 1;
  for (const b of bands) {
    if (absV >= b) {
      band = b;
      break;
    }
  }
  const leading = Math.floor(absV / band); // 1..999
  const leadingDigits = String(leading).length;
  return Math.max(0, 3 - leadingDigits);
}

/**
 * Infer the storage magnitude of a series from its formatting suffix.
 *
 * Returns the factor F such that the underlying raw value (in base units —
 * raw dollars, raw people, etc.) equals `stored × F`. Pure heuristic that
 * reads `formatting.suffix` for canonical ' B', ' M', ' T', ' K' markers.
 * Everything else returns 1 (treated as raw).
 *
 * Used by the multi-source chart renderer to put mixed-magnitude series
 * on a common y-axis — without this, a $700 share price plots HIGHER
 * than a 300 (=$300B) market cap because both are read at face value.
 *
 * Bias note: this only catches sources that opted into a suffix in their
 * formatting block. Sources that store billions but rely on
 * `notation: "compact"` to render the unit have `scaleFactor` set to 1e9
 * instead — fall back to that as the secondary signal.
 */
export function magnitudeFromFormatting(fmt: Formatting): number {
  const suffix = (fmt.suffix ?? "").trim();
  switch (suffix) {
    case "T":
      return 1e12;
    case "B":
      return 1e9;
    case "M":
      return 1e6;
    case "K":
      return 1e3;
  }
  // Compact notation that pulls its rendered suffix from scaleFactor.
  // e.g. a series stored in billions can opt to ship as `notation: compact,
  // scaleFactor: 1e9` so the formatted readout autoselects T/B/M based on
  // magnitude. The scaleFactor itself IS the storage magnitude.
  if (fmt.notation === "compact" && fmt.scaleFactor && fmt.scaleFactor > 1) {
    return fmt.scaleFactor;
  }
  return 1;
}

export function formatValue(v: number, fmt: Formatting): string {
  // Apply the scaleFactor (if any) before everything else — both the
  // compact-decimals heuristic and Intl.NumberFormat use the scaled
  // value. Defaults to 1 so existing-no-scaleFactor sources are
  // unchanged.
  const scaled = v * (fmt.scaleFactor ?? 1);
  const isCompact = fmt.notation === "compact";
  const decimals = isCompact ? compactDecimalsFor(scaled) : fmt.decimals;
  const opts: Intl.NumberFormatOptions = {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  };
  if (isCompact) {
    opts.notation = "compact";
    opts.compactDisplay = "short";
  }

  let formatted: string;
  switch (fmt.style) {
    case "currency":
      formatted = new Intl.NumberFormat("en-US", {
        ...opts,
        style: "currency",
        currency: fmt.currency ?? "USD",
      }).format(scaled);
      break;
    case "percent":
      // Values are already in percentage terms (e.g., 4.42 means 4.42%).
      formatted = new Intl.NumberFormat("en-US", opts).format(scaled) + "%";
      break;
    case "bps":
      formatted = `${new Intl.NumberFormat("en-US", opts).format(scaled)} bps`;
      break;
    case "index":
    case "number":
    default:
      formatted = new Intl.NumberFormat("en-US", opts).format(scaled);
  }

  if (fmt.prefix) formatted = fmt.prefix + formatted;
  if (fmt.suffix) formatted = formatted + fmt.suffix;
  // Swap the ASCII hyphen-minus (U+002D) for the typographic Unicode
  // minus sign (U+2212) on negative values. The Inter / system-font
  // hyphen-minus glyph is thin and short — at chart-axis sizes
  // (10-11px) it visually disappears, making "-1,000.0%" read as
  // "1,000.0%" in screenshots and on dense plots. The Unicode minus
  // is wider + more horizontal so it survives downscaling. Intl
  // doesn't expose a knob for this, so we replace post-hoc. Only
  // touches the leading sign — internal dashes (e.g. inside an
  // accounting-style "(123)" placeholder, dates, ISO strings) stay
  // alone because formatValue never emits those.
  if (formatted.startsWith("-")) {
    formatted = "−" + formatted.slice(1);
  }
  return formatted;
}

export function formatSignedValue(v: number, fmt: Formatting): string {
  const base = formatValue(Math.abs(v), fmt);
  return v >= 0 ? `+${base}` : `\u2212${base}`;
}

/**
 * Formatting for y-axis TICK labels specifically. The plot's left margin
 * is narrow (~64px), so a long word suffix makes every tick read like
 * "3.4 workers" (~11 chars) \u2014 which overflows the margin and gets its
 * leading characters clipped, leaving nonsense like "4 workers",
 * "2 workers", "0 workers" (just the trailing decimal digit). Strip
 * such word/unit suffixes from the axis; the unit still appears in the
 * chart title, the big readout, and the hover tooltip. Short magnitude /
 * symbol markers (" B", " M", " T", " K", "%") are 1 char after trimming
 * and ARE the axis scale, so they stay. The prefix (e.g. "$") is left
 * untouched \u2014 it's always short and carries the unit.
 */
export function axisTickFormatting(fmt: Formatting): Formatting {
  const trimmed = (fmt.suffix ?? "").trim();
  if (trimmed.length <= 1) return fmt;
  return { ...fmt, suffix: undefined };
}

/**
 * Compact delta display string. For percent-style sources only the absolute
 * delta is shown — the relative change is meaningless (and often misleading)
 * for rate-like series with near-zero baselines: a 2-year Treasury that ran
 * 0.14% → 4.01% in five years has a relative change of +2,764%, which is
 * pure noise next to the +3.87 pp move that actually matters. Non-percent
 * series keep the relative %change.
 *
 *   non-percent:  "+2.4%"     (relative)
 *   percent:      "+0.2%"     (absolute pp — `.pct` is still exposed for
 *                              callers that want the relative on hover etc.)
 */
export function formatDeltaDisplay(
  current: number,
  prior: number,
  fmt: Formatting,
): {
  text: string;
  pct: string;
  abs: string;
  direction: "up" | "down" | "flat";
} {
  const d = formatDelta(current, prior, fmt);
  const text = fmt.style === "percent" ? d.abs : d.pct;
  return { text, pct: d.pct, abs: d.abs, direction: d.direction };
}

export function formatDelta(
  current: number,
  prior: number,
  fmt: Formatting,
): { abs: string; pct: string; direction: "up" | "down" | "flat" } {
  const diff = current - prior;
  const pct = prior !== 0 ? (diff / Math.abs(prior)) * 100 : 0;

  const direction =
    Math.abs(diff) < 1e-9 ? "flat" : diff > 0 ? "up" : "down";

  const absFmt: Formatting = { ...fmt, decimals: fmt.decimals };
  const abs = formatValue(diff, absFmt);

  const pctFmt = new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    signDisplay: "exceptZero",
  });

  // pctFmt.format(...) emits an ASCII hyphen-minus (U+002D) for the
  // negative sign — same legibility problem as formatValue (axis-
  // size renders read as positive). Swap to Unicode minus here too.
  // signDisplay:"exceptZero" guarantees the sign is the leading
  // character for non-zero values, so a startsWith check is safe.
  let pctStr = pctFmt.format(pct);
  if (pctStr.startsWith("-")) {
    pctStr = "−" + pctStr.slice(1);
  }

  return {
    abs: diff >= 0 ? `+${abs}` : abs,
    pct: `${pctStr}%`,
    direction,
  };
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}
