/* Verify frontend syntax against the original or a tested feature baseline. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const parser = require("@babel/parser");

// Naming-file fields and highlights are covered by browser scenarios.
const featureBaselines = {
  // Dashboard refresh and frozen panes are covered by browser scenarios.
  "coverage.html": "297ed15",
  "index.html": "0b6d6dc",
  "quality.html": "0b6d6dc",
  "search.html": "0b6d6dc",
  "ingestion.html": "6380c2d",
  "capture_review.js": "0b6d6dc",
  "fields.js": "0b6d6dc",
};
const files = [
  "capture_review.js",
  "fields.js",
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
  const revision = process.argv[2] || featureBaselines[filename] || "808746d";
  const revisionFiles = new Set(
    execFileSync("git", ["ls-tree", "-r", "--name-only", revision], {
      encoding: "utf8",
    }).split("\n"),
  );
  const directory = filename.endsWith(".html") ? "pages" : "static/js";
  const currentPath = path.join("web", directory, filename);
  const originalPath = revisionFiles.has(currentPath) ? currentPath : filename;
  const original = execFileSync(
    "git",
    ["show", `${revision}:${originalPath}`],
    {
      encoding: "utf8",
    },
  );
  const current = fs.readFileSync(currentPath, "utf8");
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

// Project behavior is exercised by the real upload and navigation browser scenario.
for (const filename of ["project_context.js", "projects.js"]) {
  parser.parse(fs.readFileSync(path.join("web/static/js", filename), "utf8"));
  console.log(`PASS ${filename}: JavaScript parses`);
}
