import { readFile } from "node:fs/promises";

const target = process.argv[2];
if (!target) {
  throw new Error(
    "Usage: npm run security:csp:verify -- https://your-deployed-frontend.example",
  );
}

const config = JSON.parse(await readFile(new URL("../vercel.json", import.meta.url), "utf8"));
const route = config.headers.find(({ source }) => source === "/(.*)");
const expected = route?.headers.find(
  ({ key }) => key.toLowerCase() === "content-security-policy",
)?.value;

if (!expected) throw new Error("No production CSP is configured in frontend/vercel.json");

const response = await fetch(target, { redirect: "follow" });
if (!response.ok) {
  throw new Error(`Deployment returned HTTP ${response.status} for ${response.url}`);
}

const actual = response.headers.get("content-security-policy");
if (!actual) {
  throw new Error("The deployed response does not include Content-Security-Policy");
}
if (actual.trim() !== expected.trim()) {
  throw new Error(
    [
      "The served CSP does not match frontend/vercel.json.",
      `Expected: ${expected}`,
      `Received: ${actual}`,
    ].join("\n"),
  );
}

console.log(`Verified deployed CSP on ${response.url}`);
console.log(actual);
