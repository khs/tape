import { describe, it, expect } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown — paragraphs + inline", () => {
  it("wraps a single line in <p>", () => {
    expect(renderMarkdown("hello world")).toBe("<p>hello world</p>");
  });

  it("escapes HTML in plain text", () => {
    expect(renderMarkdown("<script>alert(1)</script>")).toBe(
      "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>",
    );
  });

  it("renders **bold** + *italic* together", () => {
    expect(renderMarkdown("**hot** take is *fine*")).toBe(
      "<p><strong>hot</strong> take is <em>fine</em></p>",
    );
  });

  it("renders __bold__ alternate syntax", () => {
    expect(renderMarkdown("__loud__")).toBe(
      "<p><strong>loud</strong></p>",
    );
  });

  it("renders inline `code`", () => {
    expect(renderMarkdown("use `git commit`")).toBe(
      "<p>use <code>git commit</code></p>",
    );
  });

  it("escapes HTML inside inline code", () => {
    expect(renderMarkdown("`<script>`")).toBe(
      "<p><code>&lt;script&gt;</code></p>",
    );
  });

  it("joins lines within a paragraph with a space", () => {
    expect(renderMarkdown("line one\nline two")).toBe(
      "<p>line one line two</p>",
    );
  });

  it("emits <br/> when a line ends with two spaces", () => {
    expect(renderMarkdown("line one  \nline two")).toBe(
      "<p>line one<br/>line two</p>",
    );
  });

  it("breaks paragraphs on blank lines", () => {
    expect(renderMarkdown("first para\n\nsecond para")).toBe(
      "<p>first para</p>\n<p>second para</p>",
    );
  });
});

describe("renderMarkdown — links", () => {
  it("renders a basic https link with target+rel", () => {
    expect(renderMarkdown("see [docs](https://example.com)")).toBe(
      '<p>see <a href="https://example.com" target="_blank" rel="noopener noreferrer">docs</a></p>',
    );
  });

  it("renders a relative (/-rooted) link without target+rel", () => {
    expect(renderMarkdown("[home](/)")).toBe(
      '<p><a href="/">home</a></p>',
    );
  });

  it("allows http://", () => {
    const out = renderMarkdown("[x](http://insecure.example)");
    expect(out).toContain('href="http://insecure.example"');
  });

  it("allows mailto:", () => {
    const out = renderMarkdown("[mail](mailto:foo@bar.com)");
    expect(out).toContain('href="mailto:foo@bar.com"');
  });

  it("drops javascript: URLs (renders link text, no anchor)", () => {
    // The URL parser stops at the first `)` so the inner `)` of
    // alert(1) gets treated as the URL terminator. What matters
    // for security: no <a href="javascript:..."> tag is emitted.
    // The stray `)` left over by the unbalanced parenthesis is
    // acceptable cosmetic noise from a malicious input.
    const out = renderMarkdown("[click](javascript:alert(1))");
    expect(out).not.toContain("href=\"javascript:");
    expect(out).not.toContain("<a ");
    expect(out).toContain("click");
  });

  it("drops data: URLs", () => {
    expect(renderMarkdown("[click](data:text/html,<script>)")).toBe(
      "<p>click</p>",
    );
  });

  it("escapes quote chars in URLs", () => {
    expect(renderMarkdown('[x](https://a?q="evil)')).toContain("&quot;evil");
  });
});

describe("renderMarkdown — block structure", () => {
  it("renders ## headings as h2", () => {
    expect(renderMarkdown("## Big idea")).toBe("<h2>Big idea</h2>");
  });

  it("renders ### as h3 and #### as h4", () => {
    expect(renderMarkdown("### A\n#### B")).toBe("<h3>A</h3>\n<h4>B</h4>");
  });

  it("does not promote a # (h1) heading — h1 stays as plain text", () => {
    // h1 is reserved for the dashboard title.
    expect(renderMarkdown("# Title")).toBe("<p># Title</p>");
  });

  it("groups consecutive bullet lines into one <ul>", () => {
    expect(renderMarkdown("- alpha\n- beta\n- gamma")).toBe(
      "<ul><li>alpha</li><li>beta</li><li>gamma</li></ul>",
    );
  });

  it("groups numbered lines into one <ol>", () => {
    expect(renderMarkdown("1. first\n2. second")).toBe(
      "<ol><li>first</li><li>second</li></ol>",
    );
  });

  it("renders fenced code blocks with HTML escaped", () => {
    const md = "```\n<script>alert(1)</script>\n```";
    expect(renderMarkdown(md)).toBe(
      "<pre><code>&lt;script&gt;alert(1)&lt;/script&gt;</code></pre>",
    );
  });

  it("renders bold inside a heading", () => {
    expect(renderMarkdown("## **strong** title")).toBe(
      "<h2><strong>strong</strong> title</h2>",
    );
  });

  it("renders an inline link inside a list item", () => {
    expect(renderMarkdown("- see [docs](/docs)")).toBe(
      '<ul><li>see <a href="/docs">docs</a></li></ul>',
    );
  });
});

describe("renderMarkdown — security", () => {
  it("doesn't pass-through raw HTML tags", () => {
    expect(renderMarkdown("<img src=x onerror=alert(1)>")).toBe(
      "<p>&lt;img src=x onerror=alert(1)&gt;</p>",
    );
  });

  it("rejects <a> tags directly written by the user", () => {
    const out = renderMarkdown('<a href="javascript:alert(1)">x</a>');
    // Should be entity-escaped — no real anchor emitted.
    expect(out).not.toContain('<a href="javascript');
    expect(out).toContain("&lt;a href=");
  });

  it("escapes HTML inside link text", () => {
    const out = renderMarkdown('[<img>](https://example.com)');
    expect(out).toContain("&lt;img&gt;");
    expect(out).not.toContain("<img>");
  });

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });
});
