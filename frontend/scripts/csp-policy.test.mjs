import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");
const config = JSON.parse(await read("../vercel.json"));
const layout = await read("../src/app/layout.tsx");
const themeBootstrap = await read("../public/theme-bootstrap.js");

function getCsp() {
  const route = config.headers.find(({ source }) => source === "/(.*)");
  assert.ok(route, "Vercel must apply security headers to every frontend route");
  const header = route.headers.find(({ key }) => key.toLowerCase() === "content-security-policy");
  assert.ok(header, "Vercel must emit a Content-Security-Policy header");
  return header.value;
}

function directives(policy) {
  return Object.fromEntries(
    policy.split(";").map((part) => {
      const [name, ...values] = part.trim().split(/\s+/);
      return [name, values];
    }),
  );
}

test("production CSP removes unsafe-eval", () => {
  const scriptSources = directives(getCsp())["script-src"];
  assert.ok(scriptSources.includes("'self'"));
  assert.ok(!scriptSources.includes("'unsafe-eval'"));
});

test("connect-src is an explicit same-origin and backend allowlist", () => {
  const sources = directives(getCsp())["connect-src"];
  assert.deepEqual(sources, [
    "'self'",
    "https://assembly-backend.onrender.com",
    "wss://assembly-backend.onrender.com",
  ]);
  assert.ok(!sources.some((source) => source.includes("*")));
});

test("the only script-src inline exception is documented for static App Router output", async () => {
  const sources = directives(getCsp())["script-src"];
  assert.deepEqual(sources, ["'self'", "'unsafe-inline'"]);
  const documentation = await read("../../docs/csp.md");
  assert.match(documentation, /Next\.js App Router.*inline Flight/i);
  assert.match(documentation, /static[- ]export/i);
});

function runThemeBootstrap(savedTheme, systemDark) {
  const toggles = [];
  let matchMediaCalls = 0;

  vm.runInNewContext(themeBootstrap, {
    window: {
      localStorage: { getItem: () => savedTheme },
      matchMedia: (query) => {
        matchMediaCalls += 1;
        assert.equal(query, "(prefers-color-scheme: dark)");
        return { matches: systemDark };
      },
    },
    document: {
      documentElement: {
        classList: {
          toggle: (token, force) => toggles.push({ token, force }),
        },
      },
    },
  });

  return { toggles, matchMediaCalls };
}

test("the application theme bootstrap is parser-blocking in the document head", () => {
  assert.match(
    layout,
    /<head>\s*<script id="assembly-theme-bootstrap" src="\/theme-bootstrap\.js"\s*\/>\s*<\/head>/,
  );
  assert.doesNotMatch(layout, /from "next\/script"/);
  assert.doesNotMatch(layout, /<Script\b/);
  assert.match(themeBootstrap, /localStorage\.getItem\("assembly:theme"\)/);
  assert.match(themeBootstrap, /prefers-color-scheme: dark/);
});

test("the theme bootstrap applies a saved dark preference without consulting the system", () => {
  assert.deepEqual(runThemeBootstrap("dark", false), {
    toggles: [{ token: "dark", force: true }],
    matchMediaCalls: 0,
  });
});

test("the theme bootstrap applies both system preference outcomes when no theme is saved", () => {
  assert.deepEqual(runThemeBootstrap(null, true), {
    toggles: [{ token: "dark", force: true }],
    matchMediaCalls: 1,
  });
  assert.deepEqual(runThemeBootstrap(null, false), {
    toggles: [{ token: "dark", force: false }],
    matchMediaCalls: 1,
  });
});
