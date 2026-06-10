/**
 * Serialize a value for embedding in an inline `<script>` element
 * (e.g. `<script type="application/json">` data islands and JSON-LD).
 *
 * Why this exists: `JSON.stringify` does NOT escape `<`, so a string
 * value containing the literal `</script>` (or `<!--`) terminates the
 * surrounding raw-text `<script>` element early in the HTML tokenizer
 * and lets everything after it be parsed as HTML — a classic stored/
 * reflected XSS when any serialized value is user-controlled. In this
 * app that includes inline-chart titles, blurbs, annotation labels,
 * and the full composed state echoed by `/custom?d=…` (no auth needed
 * to deliver the payload, and there is no CSP backstop).
 *
 * Escaping `<` to its `<` unicode escape prevents both the
 * `</script>` and `<!--` breakouts and is fully transparent to
 * `JSON.parse` (and to JSON-LD consumers): `JSON.parse('"\\u003c"')`
 * === "<". That single substitution is sufficient for an HTML inline-
 * script context; we deliberately keep it minimal.
 *
 * Use this for EVERY `set:html={JSON.stringify(x)}` in an inline script
 * tag, not just the ones with obviously-user data — uniform use is the
 * maintainable invariant (no "why is this one escaped and that one not").
 */
export function jsonForScript(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}
