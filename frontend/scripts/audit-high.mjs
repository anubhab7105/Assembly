// CI gate: npm audit at high level with an explicit allowlist for
// known-unpatchable transitive advisories.
// Usage: node scripts/audit-high.mjs (exit 0 = pass, 1 = blocking vulns or audit failure)
import { exec } from "node:child_process";
import { promisify } from "node:util";

const execAsync = promisify(exec);

export const ALLOWLIST = [
  {
    ghsa: "GHSA-vfj7-8cjw-p6xm",
    package: "braces",
    owner: "assembly-maintainers",
    reviewBy: "2027-01-12",
    reason:
      "braces <=3.0.3 has no patched version; transitive via micromatch/fast-glob from shadcn and eslint-config-next dev tooling. npm audit fix is a no-op and --force wants a breaking shadcn 4.x -> 1.0.0 downgrade.",
  },
  {
    ghsa: "GHSA-mrhx-c7xc-m3w5",
    package: "zod",
    owner: "assembly-maintainers",
    reviewBy: "2026-11-07",
    reason:
      "The root Zod dependency is upgraded to 4.6.7. shadcn 4.21.4 and @shadcn/registry 0.1.3 still pin nested Zod 3.x; forcing Zod 4 into this CLI chain may break its Zod-3-oriented schema tooling. Temporary, scoped exception for the maintainer-run CLI only; remove when upstream ships a compatible patched release.",
  },
];

export function advisoryDetailsFromVia(via) {
  const out = [];
  for (const entry of via ?? []) {
    if (typeof entry === "object" && entry !== null && typeof entry.url === "string") {
      const m = entry.url.match(/GHSA-[a-z0-9-]+/i);
      if (m) {
        out.push({
          id: m[0].toLowerCase(),
          // npm audit advisory objects carry the vulnerable package name.
          package: typeof entry.name === "string" ? entry.name : null,
        });
      }
    }
  }
  return out;
}

// Fail closed: any audit-service error or malformed/incomplete report throws.
export function validateReport(report) {
  if (report === null || typeof report !== "object" || Array.isArray(report)) {
    throw new Error("audit-high: report is not an object (refusing to pass).");
  }
  if ("error" in report && report.error != null) {
    const err = report.error;
    const summary =
      typeof err === "object" && err !== null && "summary" in err
        ? String(err.summary)
        : JSON.stringify(err).slice(0, 500);
    throw new Error(`audit-high: npm audit service error: ${summary}`);
  }
  if (
    !("vulnerabilities" in report) ||
    report.vulnerabilities === null ||
    typeof report.vulnerabilities !== "object" ||
    Array.isArray(report.vulnerabilities)
  ) {
    throw new Error(
      "audit-high: report has no vulnerabilities object (refusing to pass)."
    );
  }
  return report.vulnerabilities;
}

export function collectBlocking(report) {
  const vulns = validateReport(report);
  // Match on (ghsa, package) — the package field is enforced, not decorative.
  const allow = new Map(
    ALLOWLIST.map((a) => [`${a.ghsa.toLowerCase()}@${a.package}`, a])
  );
  const blocking = [];
  const allowlisted = [];

  const resolveAdvisories = (name, seen = new Set()) => {
    if (seen.has(name)) return [];
    seen.add(name);
    const v = vulns[name];
    if (!v) return [];
    const direct = advisoryDetailsFromVia(v.via);
    const nested = (v.via ?? [])
      .filter((e) => typeof e === "string")
      .flatMap((dep) => resolveAdvisories(dep, seen));
    return [...direct, ...nested];
  };

  for (const [name, v] of Object.entries(vulns)) {
    if (v.severity !== "high" && v.severity !== "critical") continue;
    const resolved = resolveAdvisories(name);
    // Dedupe on id@package.
    const uniq = [
      ...new Map(resolved.map((r) => [`${r.id}@${r.package}`, r])).values(),
    ];
    const unlisted = uniq.filter((r) => !allow.has(`${r.id}@${r.package}`));
    // Empty advisory set is NOT coverage — fail closed (blocking).
    if (uniq.length > 0 && unlisted.length === 0) {
      allowlisted.push({
        name,
        severity: v.severity,
        ids: uniq.map((r) => r.id),
      });
    } else {
      blocking.push({
        name,
        severity: v.severity,
        ids: uniq.map((r) => `${r.id}${r.package ? ` (${r.package})` : ""}`),
        range: v.range,
      });
    }
  }
  return { blocking, allowlisted };
}

function printAllowlistHeader() {
  for (const a of ALLOWLIST) {
    console.log(
      `audit-high: exception ${a.ghsa} on package ${a.package} — owner ${a.owner}, review by ${a.reviewBy}`
    );
    console.log(`audit-high:   reason: ${a.reason}`);
  }
}

async function main() {
  let stdout;
  try {
    ({ stdout } = await execAsync("npm audit --json", {
      maxBuffer: 32 * 1024 * 1024,
    }));
  } catch (err) {
    // npm audit exits 1 when vulns are found but still prints JSON to stdout.
    // No stdout at all (spawn failure, killed process) is a hard failure.
    if (!err.stdout) throw err;
    stdout = err.stdout;
  }
  let report;
  try {
    report = JSON.parse(stdout);
  } catch (err) {
    console.error("audit-high: failed to parse `npm audit --json` output.");
    throw err;
  }
  // Fail closed on service errors / malformed reports (throws -> nonzero exit).
  const { blocking, allowlisted } = collectBlocking(report);
  printAllowlistHeader();
  for (const a of allowlisted) {
    console.log(
      `audit-high: allowlisted ${a.name} [${a.severity}] (${a.ids.join(", ")})`
    );
  }
  if (blocking.length === 0) {
    console.log(
      `audit-high: PASS (${allowlisted.length} allowlisted, 0 blocking high/critical)`
    );
    return;
  }
  console.error(
    `audit-high: FAIL (${blocking.length} blocking high/critical vulnerabilities)`
  );
  for (const b of blocking) {
    console.error(
      `- ${b.name} [${b.severity}] range ${b.range} advisories: ${b.ids.join(", ") || "unknown"}`
    );
  }
  process.exitCode = 1;
}

const isMain =
  process.argv[1] != null &&
  import.meta.url.endsWith(
    process.argv[1].replaceAll("\\", "/").split("/").pop() ?? ""
  );
if (isMain) {
  await main();
}
