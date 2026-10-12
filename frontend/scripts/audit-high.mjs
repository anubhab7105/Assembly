// CI gate: npm audit at high level with an explicit allowlist for
// known-unpatchable transitive advisories.
// Usage: node scripts/audit-high.mjs (exit 0 = pass, 1 = blocking vulns)
import { exec } from "node:child_process";
import { promisify } from "node:util";

const execAsync = promisify(exec);

const ALLOWLIST = [
  {
    ghsa: "GHSA-vfj7-8cjw-p6xm",
    package: "braces",
    reason:
      "braces <=3.0.3 has no patched version; transitive via micromatch/fast-glob from shadcn and eslint-config-next dev tooling. npm audit fix is a no-op and --force wants a breaking shadcn 4.x -> 1.0.0 downgrade.",
  },
];

function advisoryIdsFromVia(via) {
  const ids = [];
  for (const entry of via ?? []) {
    if (typeof entry === "object" && entry !== null && typeof entry.url === "string") {
      const m = entry.url.match(/GHSA-[a-z0-9-]+/i);
      if (m) ids.push(m[0].toLowerCase());
    }
  }
  return ids;
}

function collectBlocking(report) {
  const vulns = report.vulnerabilities ?? {};
  const allow = new Set(ALLOWLIST.map((a) => a.ghsa.toLowerCase()));
  const blocking = [];
  const allowlisted = [];

  const resolveAdvisories = (name, seen = new Set()) => {
    if (seen.has(name)) return [];
    seen.add(name);
    const v = vulns[name];
    if (!v) return [];
    const direct = advisoryIdsFromVia(v.via);
    const nested = (v.via ?? [])
      .filter((e) => typeof e === "string")
      .flatMap((dep) => resolveAdvisories(dep, seen));
    return [...direct, ...nested];
  };

  for (const [name, v] of Object.entries(vulns)) {
    if (v.severity !== "high" && v.severity !== "critical") continue;
    const ids = [...new Set(resolveAdvisories(name))];
    const unlisted = ids.filter((id) => !allow.has(id));
    // No advisory object found (only string chain to an allowlisted root counts
    // via recursion above); if ids is empty the vuln is not covered -> blocking.
    if (ids.length > 0 && unlisted.length === 0) {
      allowlisted.push({ name, severity: v.severity, ids });
    } else {
      blocking.push({ name, severity: v.severity, ids, range: v.range });
    }
  }
  return { blocking, allowlisted };
}

async function main() {
  let stdout;
  try {
    ({ stdout } = await execAsync("npm audit --json", {
      maxBuffer: 32 * 1024 * 1024,
    }));
  } catch (err) {
    // npm audit exits 1 when vulns are found but still prints JSON to stdout.
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
  const { blocking, allowlisted } = collectBlocking(report);
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

await main();
