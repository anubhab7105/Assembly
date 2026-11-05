# Frontend Content Security Policy

The authoritative production response-header policy is in `frontend/vercel.json`. Vercel applies it to every frontend route.

## Network allowlist

The browser-side Assembly client sends API requests and opens its progress WebSocket to the same FastAPI backend origin configured by `NEXT_PUBLIC_API_URL` (or the desktop runtime's `ASSEMBLY_API_URL`). Model-provider and search-provider requests are made by the backend; the browser does not need arbitrary provider origins in `connect-src`.

The current allowlist includes:

- `https://assembly-backend.onrender.com` for FastAPI HTTP/SSE requests.
- `wss://assembly-backend.onrender.com` for the browser progress WebSocket.
- `'self'` for same-origin requests.

The Render Blueprint names the web service `assembly-backend`. Confirm the exact public hostname shown in the Render dashboard before promoting this policy. If Render assigned a different hostname or the deployment uses a custom backend domain, update both entries in `frontend/vercel.json` and the expected values in `frontend/scripts/csp-policy.test.mjs`. Keep the HTTP and WebSocket origins exact; do not replace them with `https://*`, `wss://*`, or a broad provider allowlist.

The desktop app has its own Tauri CSP in `desktop/src-tauri/tauri.conf.json`; this Vercel policy applies to the hosted frontend.

## Script policy and the static-export exception

`unsafe-eval` has been removed from `script-src`. Assembly's own theme bootstrap is now served from `/theme-bootstrap.js`, a same-origin external asset, rather than an inline `next/script` block.

The policy retains one documented `'unsafe-inline'` exception in `script-src` because this frontend currently uses the Next.js App Router with `output: "export"`. The static App Router output contains framework-generated inline Flight payload scripts (for example, `self.__next_f.push(...)`) required for client hydration. Under the current static-export deployment model, those scripts do not receive a per-response nonce; removing `'unsafe-inline'` blocks hydration. A nonce-based CSP requires a request-time rendering/proxy architecture rather than this static-export setup. See the Next.js static-export discussion: https://github.com/vercel/next.js/discussions/54152.

This exception is not permission to add application-authored inline scripts. Keep application scripts in same-origin files. Revisit and remove the exception if Assembly migrates to a runtime architecture that can apply a fresh nonce to framework and application scripts on every response. Do not reintroduce `unsafe-eval`.

The existing `style-src 'unsafe-inline'`, image, and font directives are unchanged by this remediation; they should be assessed separately with evidence from the rendered UI.

## Verification

Run from `frontend/`:

```bash
npm run security:csp:test
npm run build
npx tsc --noEmit
npx playwright test
```

After Vercel has deployed the change, verify the actual response header (not just this source file):

```bash
npm run security:csp:verify -- https://assembly-murex.vercel.app
```

Then inspect the browser console and Network panel while checking the hosted app load, settings/key-vault flow, API preflight, run creation, SSE stream, and WebSocket progress. A local `next dev` run does not exercise Vercel's configured response headers.
