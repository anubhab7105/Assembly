// Regression tests for the audit-high allowlist gate.
// Run: node --test scripts/audit-high.test.mjs
// @vitest-environment node
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  ALLOWLIST,
  advisoryDetailsFromVia,
  collectBlocking,
  validateReport,
} from "./audit-high.mjs";

describe("audit-high fail-closed validation", () => {
  it("rejects npm audit service-error payloads", () => {
    assert.throws(
      () => validateReport({ error: { code: "EAUDIT", summary: "registry down" } }),
      /service error/
    );
  });

  it("rejects reports without a vulnerabilities object", () => {
    assert.throws(() => validateReport({}), /no vulnerabilities object/);
    assert.throws(() => validateReport({ vulnerabilities: null }), /no vulnerabilities/);
    assert.throws(() => validateReport({ vulnerabilities: [] }), /no vulnerabilities/);
    assert.throws(() => validateReport(null), /not an object/);
    assert.throws(() => validateReport("ok"), /not an object/);
  });

  it("treats high vulns with no advisory object as blocking (empty via)", () => {
    const report = {
      vulnerabilities: {
        "mystery-pkg": { name: "mystery-pkg", severity: "high", range: "*", via: [] },
      },
    };
    const { blocking } = collectBlocking(report);
    assert.equal(blocking.length, 1);
    assert.equal(blocking[0].name, "mystery-pkg");
  });
});

describe("audit-high allowlist enforcement", () => {
  const bracesAdvisory = {
    source: 1240992,
    name: "braces",
    dependency: "braces",
    title: "braces stack-exhaustion",
    url: "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm",
    severity: "high",
    range: "<=3.0.3",
  };

  it("passes the known braces chain including transitive string refs", () => {
    const report = {
      vulnerabilities: {
        braces: { name: "braces", severity: "high", range: "*", via: [bracesAdvisory] },
        micromatch: { name: "micromatch", severity: "high", range: ">=0.2.0", via: ["braces"] },
      },
    };
    const { blocking, allowlisted } = collectBlocking(report);
    assert.equal(blocking.length, 0);
    assert.equal(allowlisted.length, 2);
  });

  it("allowlists only the known Zod advisory while it remains in shadcn CLI dependencies", () => {
    const zodAdvisory = {
      source: 1240992,
      name: "zod",
      dependency: "zod",
      title: "Zod can exhaust memory while validating oversized constrained collections",
      url: "https://github.com/advisories/GHSA-mrhx-c7xc-m3w5",
      severity: "high",
      range: "<4.6.6",
    };
    const report = {
      vulnerabilities: {
        zod: {
          name: "zod",
          severity: "high",
          range: "<4.6.6",
          via: [zodAdvisory],
        },
        "@shadcn/registry": {
          name: "@shadcn/registry",
          severity: "high",
          range: "0.1.0 - 0.1.4",
          via: ["zod"],
        },
        shadcn: {
          name: "shadcn",
          severity: "high",
          range: "2.0.0 - 4.21.5",
          via: ["@shadcn/registry", "zod"],
        },
      },
    };
    const { blocking, allowlisted } = collectBlocking(report);
    assert.equal(blocking.length, 0);
    assert.equal(allowlisted.length, 3);
  });


  it("allowlists the known deepmerge advisory only when the package matches", () => {
    const deepmergeAdvisory = {
      source: 1240992,
      name: "deepmerge",
      dependency: "deepmerge",
      title: "deepmerge mergeObject() allows prototype poisoning of returned objects",
      url: "https://github.com/advisories/GHSA-gcqx-w48m-w2h4",
      severity: "high",
      range: ">=4.2.0 <=4.3.1",
    };
    const report = {
      vulnerabilities: {
        deepmerge: {
          name: "deepmerge",
          severity: "high",
          range: "4.2.0 - 4.3.1",
          via: [deepmergeAdvisory],
        },
        shadcn: {
          name: "shadcn",
          severity: "high",
          range: "4.21.4",
          via: ["deepmerge"],
        },
      },
    };
    const { blocking, allowlisted } = collectBlocking(report);
    assert.equal(blocking.length, 0);
    assert.equal(allowlisted.length, 2);

    const mismatchedPackage = {
      vulnerabilities: {
        "unrelated-package": {
          name: "unrelated-package",
          severity: "high",
          range: "*",
          via: [
            {
              name: "unrelated-package",
              url: "https://github.com/advisories/GHSA-gcqx-w48m-w2h4",
            },
          ],
        },
      },
    };
    assert.equal(collectBlocking(mismatchedPackage).blocking.length, 1);
  });
\n  it("blocks a synthetic new high advisory (regression)", () => {
    const report = {
      vulnerabilities: {
        "evil-pkg": {
          name: "evil-pkg",
          severity: "high",
          range: "*",
          via: [{ name: "evil-pkg", url: "https://github.com/advisories/GHSA-aaaa-bbbb-cccc" }],
        },
      },
    };
    const { blocking } = collectBlocking(report);
    assert.equal(blocking.length, 1);
    assert.equal(blocking[0].name, "evil-pkg");
  });

  it("enforces the allowlist package: same GHSA on another package blocks", () => {
    const report = {
      vulnerabilities: {
        "other-pkg": {
          name: "other-pkg",
          severity: "high",
          range: "*",
          via: [
            { name: "other-pkg", url: "https://github.com/advisories/GHSA-vfj7-8cjw-p6xm" },
          ],
        },
      },
    };
    const { blocking } = collectBlocking(report);
    assert.equal(blocking.length, 1);
  });

  it("extracts advisory package names from via objects", () => {
    const details = advisoryDetailsFromVia([bracesAdvisory]);
    assert.deepEqual(details, [{ id: "ghsa-vfj7-8cjw-p6xm", package: "braces" }]);
  });
});

describe("audit-high exception metadata", () => {
  it("records owner and review date on every entry", () => {
    assert.ok(ALLOWLIST.length >= 1);
    for (const entry of ALLOWLIST) {
      assert.ok(entry.ghsa && entry.package && entry.owner && entry.reviewBy && entry.reason);
    }
  });
});
