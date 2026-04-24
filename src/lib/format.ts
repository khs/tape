export interface Formatting {
  style: "currency" | "percent" | "number" | "index" | "bps";
  decimals: number;
  currency?: string;
  prefix?: string;
  suffix?: string;
  notation?: "standard" | "compact";
}

export function formatValue(v: number, fmt: Formatting): string {
  const opts: Intl.NumberFormatOptions = {
    minimumFractionDigits: fmt.decimals,
    maximumFractionDigits: fmt.decimals,
  };
  if (fmt.notation === "compact") {
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
