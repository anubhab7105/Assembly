/**
 * Internal navigation must use Next <Link> (client-side) so React state
 * (test statuses, inputs, catalog) survives page changes without refetch.
 * A plain <a href="/…"> forces a full reload. Vault keys now survive
 * reloads via persistent storage, but client-side routing is still the
 * intended UX (and preserves all other in-memory UI state).
 *
 * Allowed plain anchors: external URLs (https:), fragment links (#…),
 * and fully dynamic hrefs. Everything else fails this test.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const SRC = join(dirname(dirname(fileURLToPath(import.meta.url))));

function tsxFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...tsxFiles(full));
    // Guard scans app code only: test fixtures may quote example markup.
    else if (/\.test\.[tj]sx?$/.test(full)) continue;
    else if (full.endsWith(".tsx") || full.endsWith(".ts")) out.push(full);
  }
  return out;
}

// <a ... href="/internal" ...> or href={'/internal'} — but not href="#…",
// href="https:…", or href={dynamic}.
const INTERNAL_ANCHOR =
  /<a\b[^>]*href=\{?["'`](\/(?!\/)[^"'`}]*)["'`}]?/g;

const SKIP_FILES = new Set([
  // Renders markdown citation/external links; hrefs are dynamic or fragments.
  join(SRC, "components", "final-answer.tsx"),
]);

describe("internal links use Next Link", () => {
  it("has no plain <a> to internal routes", () => {
    const offenders: string[] = [];
    for (const file of tsxFiles(SRC)) {
      if (SKIP_FILES.has(file)) continue;
      const text = readFileSync(file, "utf-8");
      let match: RegExpExecArray | null;
      INTERNAL_ANCHOR.lastIndex = 0;
      while ((match = INTERNAL_ANCHOR.exec(text)) !== null) {
        const href = match[1];
        if (href.startsWith("#")) continue;
        if (/^(https?:|mailto:)/.test(href)) continue;
        if (href.includes("${")) continue;
        offenders.push(`${file}:${href}`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
