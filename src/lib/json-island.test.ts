import { describe, it, expect } from "vitest";
import { jsonForScript } from "./json-island";

describe("jsonForScript", () => {
  it("escapes < so a </script> inside a string can't close the tag", () => {
    const out = jsonForScript({ title: "</script><img src=x onerror=alert(1)>" });
    expect(out).not.toContain("</script>");
    expect(out).toContain("\\u003c/script>");
  });

  it("neutralizes <!-- comment-injection too (also starts with <)", () => {
    const out = jsonForScript({ s: "<!--<script>" });
    expect(out).not.toContain("<!--");
    expect(out).not.toContain("<script>");
  });

  it("round-trips back to the original via JSON.parse", () => {
    const value = {
      title: "</script>",
      nested: { a: "<b> & 'c'", n: 1, t: true },
      arr: [1, "<x>", null],
    };
    expect(JSON.parse(jsonForScript(value))).toEqual(value);
  });

  it("handles primitives and null", () => {
    expect(jsonForScript(null)).toBe("null");
    expect(jsonForScript(42)).toBe("42");
    expect(jsonForScript("a<b")).toBe('"a\\u003cb"');
  });
});
