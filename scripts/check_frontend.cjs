/* Verify that frontend cleanup preserves the original JavaScript behavior. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const { execFileSync } = require("node:child_process");
const parser = require("@babel/parser");

const revision = process.argv[2] || "808746d";
const files = [
  "capture_review.js",
  "image_zoom.js",
  "index.html",
  "coverage.html",
  "quality.html",
  "search.html",
  "ingestion.html",
];
const ignored = new Set([
  "start",
  "end",
  "loc",
  "extra",
  "leadingComments",
  "innerComments",
  "trailingComments",
  "comments",
  "tokens",
]);

/* Compare syntax independently of source positions, comments, and quote style. */
function normalize(value) {
  if (Array.isArray(value)) return value.map(normalize);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(
        /* Exclude formatting metadata while retaining executable syntax. */
        ([key]) => !ignored.has(key),
      )
      .map(
        /* Normalize each child node using the same comparison rules. */
        ([key, child]) => [key, normalize(child)],
      ),
  );
}

/* Extract executable scripts from a standalone JavaScript file or HTML page. */
function scripts(source, filename) {
  if (filename.endsWith(".js")) return [source];
  return [...source.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)]
    .map(
      /* Retain each script body in its original execution order. */
      (match) => match[1],
    )
    .filter(
      /* Skip external script tags without inline JavaScript. */
      (script) => script.trim(),
    );
}

for (const filename of files) {
  const original = execFileSync("git", ["show", `${revision}:${filename}`], {
    encoding: "utf8",
  });
  const current = fs.readFileSync(filename, "utf8");
  const before = scripts(original, filename).map(
    /* Parse the original scripts into comparable syntax trees. */
    (script) => normalize(parser.parse(script)),
  );
  const after = scripts(current, filename).map(
    /* Parse the refactored scripts with identical parser settings. */
    (script) => normalize(parser.parse(script)),
  );
  assert.deepEqual(after, before, `${filename}: executable JavaScript changed`);
  console.log(`PASS ${filename}: JavaScript syntax matches ${revision}`);
}
