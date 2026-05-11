export interface Formatting {
  style: "currency" | "percent" | "number" | "index" | "bps";
  decimals: number;
  currency?: string;
  prefix?: string;
  suffix?: string;
  notation?: "standard" | "compact";
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

export function formatValue(v: number, fmt: Formatting): string {
  const isCompact = fmt.notation === "compact";
  const decimals = isCompact ? compactDecimalsFor(v) : fmt.decimals;
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
      }).format(v);
      break;
    case "percent":
      // Values are already in percentage terms (e.g., 4.42 means 4.42%).
      formatted = new Intl.NumberFormat("en-US", opts).format(v) + "%";
      break;
    case "bps":
      formatted = `${new Intl.NumberFormat("en-US", opts).format(v)} bps`;
      break;
    case "index":
    case "number":
    default:
      formatted = new Intl.NumberFormat("en-US", opts).format(v);
  }

  if (fmt.prefix) formatted = fmt.prefix + formatted;
  if (fmt.suffix) formatted = formatted + fmt.suffix;
  return formatted;
}

export function formatSignedValue(v: number, fmt: Formatting): string {
  const base = formatValue(Math.abs(v), fmt);
  return v >= 0 ? `+${base}` : `\u2212${base}`;
}

/**
 * Compact delta display string. For percent-style sources the absolute delta
 * appears in parentheses after the relative change, since "+2.4% change" on a
 * series like the unemployment rate is meaningfully different from a +2.4%
 * absolute move.
 *
 *   non-percent:  "+2.4%"
 *   percent:      "+2.4% (+0.1%)"
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
  const text = fmt.style === "percent" ? `${d.pct} (${d.abs})` : d.pct;
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

  return {
    abs: diff >= 0 ? `+${abs}` : abs,
    pct: `${pctFmt.format(pct)}%`,
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
