/* eslint-disable */
export function initBrandOrbsOrbit(canvas) {
  if (!canvas) return () => {};

  let animId = 0;
  let isDisposed = false;

(() => {
      "use strict";
      const TAU = Math.PI * 2;
      const clamp01 = v => v < 0 ? 0 : v > 1 ? 1 : v;
      const smooth = v => { v = clamp01(v); return v * v * (3 - 2 * v); };
      const lerp = (a, b, m) => a + (b - a) * m;

      /* deterministic hash noise (ported from the reference orb engine) */
      const hash = (x, y) => { const n = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453; return n - Math.floor(n); };
      const vnoise = (x, y) => {
        const xi = Math.floor(x), yi = Math.floor(y);
        let fx = x - xi, fy = y - yi;
        fx = fx * fx * (3 - 2 * fx); fy = fy * fy * (3 - 2 * fy);
        const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
        return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
      };

      /* fibonacci sphere point i of n → [x,y,z] on unit sphere */
      const fib = (i, n) => {
        const ga = Math.PI * (3 - Math.sqrt(5));
        const y = 1 - 2 * (i + .5) / n;
        const r = Math.sqrt(Math.max(0, 1 - y * y));
        const th = i * ga;
        return [r * Math.cos(th), y, r * Math.sin(th)];
      };

      /* yaw+tilt rotation and orthographic projection: returns (x,y,z)→[px,py,zdepth] */
      const proj = (yaw, tilt, cx, cy, s) => {
        const st = Math.sin(tilt), ct = Math.cos(tilt);
        const sy = Math.sin(yaw), cyw = Math.cos(yaw);
        return (x, y, z) => {
          const px = x * cyw + z * sy, pz = -x * sy + z * cyw;
          const py = y * ct - pz * st, z2 = y * st + pz * ct;
          return [cx + px * s, cy - py * s, z2];
        };
      };

      /* dot radius scale for a given canvas size (reference: (size/300)^.6) */
      const rscale = S => Math.pow(S / 300, .6) * 1.65;

      /* painter: z-sorted brand-tinted dots.
         dot: {x,y,z,r,v (brightness 0..1),a,c (optional [r,g,b] accent)} */
      function paint(ctx, dots, accent, sat, rMin) {
        dots.sort((a, b) => a.z - b.z);
        for (const d of dots) {
          const al = d.a ?? 1;
          if (al < .02) continue;
          const v = clamp01(d.v);
          const g = v * 255;
          const acc = d.c || accent;
          const st = d.c ? .95 : sat;
          let r = g, gg = g, b = g;
          if (acc && st) {
            const lift = Math.min(1, v * 1.12);
            r = g * (1 - st) + acc[0] * lift * st;
            gg = g * (1 - st) + acc[1] * lift * st;
            b = g * (1 - st) + acc[2] * lift * st;
          }
          if (v > .85) { const w = (v - .85) / .15 * .45; r += (255 - r) * w; gg += (255 - gg) * w; b += (255 - b) * w; }
          ctx.fillStyle = `rgba(${r | 0},${gg | 0},${b | 0},${al})`;
          ctx.beginPath();
          ctx.arc(d.x, d.y, Math.max(rMin * 1.4, d.r * 1.3), 0, TAU);
          ctx.fill();
        }
      }

      /* ============ CLAUDE — spark burst ============ */
      function drawClaude(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .84;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const yaw = .32 * Math.sin(t * .5), tilt = .3 + .17 * Math.sin(t * .33);
        const p = proj(yaw, tilt, cx, cy, R);
        const spin = t * .17;
        const rays = o.mini ? 8 : 11;
        const perRay = o.mini ? 4 : 6;
        const dots = [];
        /* ghost silhouette ring */
        const gh = o.mini ? 10 : 22;
        for (let i = 0; i < gh; i++) {
          const a = i / gh * TAU + t * .05;
          const [x, y, z] = p(Math.cos(a), Math.sin(a), 0);
          dots.push({ x, y, z, r: .8 * rs, v: .22, a: .1 + .1 * ((z + 1) / 2) });
        }
        for (let k = 0; k < rays; k++) {
          const baseA = k / rays * TAU + (hash(k, 3.1) - .5) * .3 + spin;
          const baseL = .62 + .38 * hash(k, 7.7);
          const pulse = .5 + .5 * Math.sin(t * 1.7 - k * 1.13);
          const L = baseL * (.8 + .28 * pulse * pulse);
          for (let j = 0; j < perRay; j++) {
            const f = (j + .8) / perRay;
            const rr = .14 + f * (L - .14);
            const [x, y, z] = p(Math.cos(baseA) * rr, Math.sin(baseA) * rr, 0);
            const dep = (z + 1) / 2;
            dots.push({
              x, y, z,
              r: (.75 + 1.35 * (1 - f * .45) + .5 * dep) * rs,
              v: .38 + .38 * f + .22 * pulse * f,
              a: .55 + .45 * f
            });
          }
        }
        /* core */
        const [x0, y0, z0] = p(0, 0, 0);
        dots.push({ x: x0, y: y0, z: z0 + .01, r: 1.5 * rs, v: .92 });
        paint(ctx, dots, o.accent, .85, .3);
      }

      /* ============ SPHERE (study) — blossom knot ============ */
      function drawSphere(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .8;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(t * .26, .35 + .08 * Math.sin(t * .4), cx, cy, R);
        const rings = 6, phi = 1.13; /* ring plane tilt from vertical axis */
        const ghostN = o.mini ? 10 : 32;
        const runners = o.mini ? 1 : 2;
        const dots = [];
        for (let i = 0; i < rings; i++) {
          const a = i / rings * TAU;
          /* ring normal, arranged with 6-fold symmetry */
          const nx = Math.sin(phi) * Math.cos(a), ny = Math.cos(phi), nz = Math.sin(phi) * Math.sin(a);
          /* orthonormal basis in ring plane */
          let ux = -nz, uy = 0, uz = nx;
          const ul = Math.hypot(ux, uz) || 1; ux /= ul; uz /= ul;
          const vx = ny * uz - nz * uy, vy = nz * ux - nx * uz, vz = nx * uy - ny * ux;
          const rad = .74;
          for (let j = 0; j < ghostN; j++) {
            const th = j / ghostN * TAU;
            const gx = (ux * Math.cos(th) + vx * Math.sin(th)) * rad;
            const gy = (uy * Math.cos(th) + vy * Math.sin(th)) * rad;
            const gz = (uz * Math.cos(th) + vz * Math.sin(th)) * rad;
            const [x, y, z] = p(gx, gy, gz);
            const dep = (z + 1) / 2;
            dots.push({ x, y, z, r: (.65 + 1 * dep) * rs, v: .4 + .45 * dep, a: .4 + .6 * dep });
          }
          for (let m = 0; m < runners; m++) {
            const th = t * (i % 2 ? -.9 : .9) + i * 1.05 + m / runners * TAU;
            const gx = (ux * Math.cos(th) + vx * Math.sin(th)) * rad;
            const gy = (uy * Math.cos(th) + vy * Math.sin(th)) * rad;
            const gz = (uz * Math.cos(th) + vz * Math.sin(th)) * rad;
            const [x, y, z] = p(gx, gy, gz);
            const dep = (z + 1) / 2;
            dots.push({ x, y, z, r: (1.2 + 1.5 * dep) * rs, v: .78 + .22 * dep });
          }
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ CURSOR — the pointer ============ */
      const mkArrow = (pts, ox, oy, sc) => pts.map(([x, y]) => [(x - ox) * sc, (y - oy) * sc]);
      /* the arrow inside the Cursor logo, traced from its own path (viewBox 24), tip first.
         two long edges (18.55 / 18.90) and two short ones (10.80 / 10.93) — the logo's own proportions */
      const ARROW_CLEAN = mkArrow([[21.207, 6.338], [12.11, 22.9], [11.95, 12.1], [2.657, 6.338]], 12, 12, .08426);
      /* the cube silhouette that frames it — same transform, so the two nest exactly as they do in the logo */
      const CURSOR_HEX = mkArrow([[12, .131], [22.528, 6.19], [22.528, 17.81], [12, 23.866], [1.471, 17.81], [1.471, 6.19]], 12, 12, .08426);
      /* study: the classic pointer, tail leg and all */
      const ARROW_LEG = mkArrow([[0, 0], [0, 17], [4, 13], [7, 19.5], [10, 18], [7, 12], [12, 12]], 5.7, 11.6, .086);
      function perimeter(pts) {
        const n = pts.length, seg = [];
        let L = 0;
        for (let i = 0; i < n; i++) {
          const a = pts[i], b = pts[(i + 1) % n];
          const l = Math.hypot(b[0] - a[0], b[1] - a[1]);
          seg.push(l); L += l;
        }
        return u => {
          let d = (((u % 1) + 1) % 1) * L, i = 0;
          while (d > seg[i] && i < n - 1) { d -= seg[i]; i++; }
          const a = pts[i], b = pts[(i + 1) % n], f = seg[i] ? d / seg[i] : 0;
          return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
        };
      }
      const cleanPath = perimeter(ARROW_CLEAN), legPath = perimeter(ARROW_LEG), hexPath = perimeter(CURSOR_HEX);
      function inPoly(pts, x, y) {
        let hit = false;
        for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
          const [xi, yi] = pts[i], [xj, yj] = pts[j];
          if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
        }
        return hit;
      }
      function drawArrowOrb(ctx, S, t, o, rot, pts, path, opt) {
        const { span, fill, wob, frame, framePath } = opt;
        const cs = Math.cos(rot), sn = Math.sin(rot);
        const rp = (x, y) => [x * cs - y * sn, x * sn + y * cs];
        const cx = S / 2, cy = S / 2, R = S / 2 * .84;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const w = wob ?? 1;   /* keep the official mark close to the flat logo silhouette */
        const p = proj(.26 * w * Math.sin(t * .5), (.3 + .12 * Math.sin(t * .35)) * w, cx, cy, R);
        /* click cycle */
        const beat = 2.4, c = ((t / beat) % 1 + 1) % 1;
        const press = c < .14 ? Math.sin(c / .14 * Math.PI) : 0;
        const scale = 1 - .09 * press;
        /* one dot every fixed step of edge length, so every line is an even queue */
        let per = 0;
        for (let i = 0; i < pts.length; i++) {
          const a = pts[i], b = pts[(i + 1) % pts.length];
          per += Math.hypot(b[0] - a[0], b[1] - a[1]);
        }
        const N = Math.max(8, Math.round(per / (o.mini ? .4 : .152)));
        const dots = [];
        const tip = rp(pts[0][0], pts[0][1]);
        for (let i = 0; i < N; i++) {
          const [ax0, ay0] = path((i + .5) / N);
          const [ax, ay] = rp(ax0, ay0);
          const [x, y, z] = p(ax * scale, -ay * scale, 0);
          const dep = (z + 1) / 2;
          const tipNear = Math.max(0, 1 - Math.hypot(ax - tip[0], ay - tip[1]) / span);
          dots.push({
            x, y, z,
            r: (.85 + 1.05 * dep + .7 * tipNear) * rs,
            v: .58 + .26 * tipNear + .14 * dep + .12 * press
          });
        }
        /* interior lattice so the mark reads as a solid pointer, not an outline */
        if (fill && !o.mini) {
          let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
          for (const [px, py] of pts) { x0 = Math.min(x0, px); x1 = Math.max(x1, px); y0 = Math.min(y0, py); y1 = Math.max(y1, py); }
          const gap = .17;
          for (let gy = y0 + gap * .5; gy < y1; gy += gap) {
            for (let gx = x0 + gap * .5; gx < x1; gx += gap) {
              if (!inPoly(pts, gx, gy)) continue;
              const [ax, ay] = rp(gx, gy);
              const [x, y, z] = p(ax * scale, -ay * scale, .03);
              const dep = (z + 1) / 2;
              const tipNear = Math.max(0, 1 - Math.hypot(ax - tip[0], ay - tip[1]) / span);
              dots.push({ x, y, z, r: (.72 + .8 * dep) * rs, v: .43 + .16 * dep + .18 * tipNear, a: .85 });
            }
          }
        }
        /* the cube outline, its own even queue of dots, sat behind the arrow */
        if (frame) {
          let fper = 0;
          for (let i = 0; i < frame.length; i++) {
            const a = frame[i], b = frame[(i + 1) % frame.length];
            fper += Math.hypot(b[0] - a[0], b[1] - a[1]);
          }
          const FN = Math.max(6, Math.round(fper / (o.mini ? .44 : .152)));
          for (let i = 0; i < FN; i++) {
            const [fx0, fy0] = framePath((i + .5) / FN);
            const [fx, fy] = rp(fx0, fy0);
            const [x, y, z] = p(fx * scale, -fy * scale, -.05);
            const dep = (z + 1) / 2;
            dots.push({ x, y, z, r: (.78 + .68 * dep) * rs, v: .46 + .16 * dep, a: .8 });
          }
        }
        /* click ripple expanding from the tip */
        const rip = c < .5 ? c / .5 : 0;
        if (rip > 0 && !o.mini) {
          const rr = .22 + .72 * rip, Nr = 14;
          for (let i = 0; i < Nr; i++) {
            const a = i / Nr * TAU;
            const [x, y, z] = p(tip[0] + Math.cos(a) * rr, -(tip[1] + Math.sin(a) * rr), -.05);
            dots.push({ x, y, z, r: .7 * rs, v: .62, a: (1 - rip) * .5 });
          }
        }
        paint(ctx, dots, null, 0, .3);
      }
      /* official: pointing right and a little up, like the logo */
      function drawCursor(ctx, S, t, o) {
        drawArrowOrb(ctx, S, t, o, 0, ARROW_CLEAN, cleanPath,
          { span: 1.5, fill: true, wob: .5, frame: CURSOR_HEX, framePath: hexPath });
      }
      /* study: the original up-left pointer */
      function drawPointer(ctx, S, t, o) { drawArrowOrb(ctx, S, t, o, 0, ARROW_LEG, legPath, { span: 1.05 }); }

      /* ============ CUBE (study) — face sweep ============ */
      const CUBE_V = [];
      for (let i = 0; i < 8; i++) CUBE_V.push([(i & 1 ? 1 : -1), (i & 2 ? 1 : -1), (i & 4 ? 1 : -1)]);
      const CUBE_E = [[0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7]];
      const CUBE_F = [[0, 1, 3, 2], [4, 5, 7, 6], [0, 1, 5, 4], [2, 3, 7, 6], [0, 2, 6, 4], [1, 3, 7, 5]];
      const CUBE_PATH = [0, 1, 3, 2, 6, 7, 5, 4]; /* gray-code loop over vertices */
      function drawCube(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .8;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.63 + t * .38, .6155 + .06 * Math.sin(t * .5), cx, cy, R);
        const h = .62;
        const perEdge = o.mini ? 4 : 8;
        /* face sweep: one face pulses at a time */
        const cyc = t * .55;
        const face = Math.floor(cyc % 6);
        const pulse = Math.sin(clamp01(cyc % 1) * Math.PI);
        const inFace = CUBE_F[face];
        const dots = [];
        for (const [a, b] of CUBE_E) {
          const hot = inFace.includes(a) && inFace.includes(b) ? pulse : 0;
          const A = CUBE_V[a], B = CUBE_V[b];
          for (let j = 0; j < perEdge; j++) {
            const f = (j + .5) / perEdge;
            const [x, y, z] = p(lerp(A[0], B[0], f) * h, lerp(A[1], B[1], f) * h, lerp(A[2], B[2], f) * h);
            const dep = (z + 1) / 2;
            dots.push({
              x, y, z,
              r: (.8 + 1.5 * dep + .5 * hot) * rs,
              v: .42 + .44 * dep + .28 * hot,
              a: .55 + .45 * dep
            });
          }
        }
        /* corner anchors */
        for (const V of CUBE_V) {
          const [x, y, z] = p(V[0] * h, V[1] * h, V[2] * h);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (1.2 + 1.5 * dep) * rs, v: .52 + .4 * dep });
        }
        /* the runner "cursor" walking the edges */
        const walk = t * .8;
        const seg = Math.floor(walk % 8), fseg = walk % 1;
        const A = CUBE_V[CUBE_PATH[seg]], B = CUBE_V[CUBE_PATH[(seg + 1) % 8]];
        for (let k = 0; k < 4; k++) {
          const f = clamp01(fseg - k * .09);
          const [x, y, z] = p(lerp(A[0], B[0], f) * h, lerp(A[1], B[1], f) * h, lerp(A[2], B[2], f) * h);
          dots.push({ x, y, z: z + .02, r: (1.7 - k * .3) * rs, v: .96 - k * .17, a: 1 - k * .2 });
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ GEMINI — astroid twinkle ============ */
      function drawGemini(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .84;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const yaw = .3 * Math.sin(t * .45), tilt = .32 + .14 * Math.sin(t * .28);
        const p = proj(yaw, tilt, cx, cy, R);
        const rotW = .14 * Math.sin(t * .9);          /* twinkle wobble */
        const scale = .88 + .12 * Math.sin(t * 1.8);  /* twinkle breath */
        const N = o.mini ? 22 : 58;
        const dots = [];
        const cBlue = [64, 148, 255], cPurple = [176, 118, 240], cPink = [225, 118, 178];
        const grad = py => {
          /* vertical gradient: top blue → mid purple → bottom pink (screen up = +py) */
          const gpos = clamp01((1 - py) / 2);
          return gpos < .5
            ? [lerp(cBlue[0], cPurple[0], gpos * 2), lerp(cBlue[1], cPurple[1], gpos * 2), lerp(cBlue[2], cPurple[2], gpos * 2)]
            : [lerp(cPurple[0], cPink[0], gpos * 2 - 1), lerp(cPurple[1], cPink[1], gpos * 2 - 1), lerp(cPurple[2], cPink[2], gpos * 2 - 1)];
        };
        for (let i = 0; i < N; i++) {
          const th = i / N * TAU + rotW;
          const c3 = Math.cos(th), s3 = Math.sin(th);
          const px = c3 * c3 * c3 * scale, py = s3 * s3 * s3 * scale;
          const [x, y, z] = p(px, py, 0);
          const dep = (z + 1) / 2;
          const tip = Math.pow(Math.abs(px) + Math.abs(py), 1.6); /* brighter near the 4 points */
          dots.push({
            x, y, z,
            r: (.7 + 1.1 * dep + .9 * tip) * rs,
            v: .48 + .32 * tip + .2 * dep,
            c: grad(py)
          });
        }
        /* inner echo star for body */
        const Ni = o.mini ? 0 : N >> 1;
        for (let i = 0; i < Ni; i++) {
          const th = i / Ni * TAU - rotW * .6;
          const c3 = Math.cos(th), s3 = Math.sin(th);
          const px = c3 * c3 * c3 * scale * .48, py = s3 * s3 * s3 * scale * .48;
          const [x, y, z] = p(px, py, .04);
          dots.push({ x, y, z, r: .85 * rs, v: .52, a: .8, c: grad(py * 2) });
        }
        /* orbiting satellite sparkles */
        if (!o.mini) for (let k = 0; k < 3; k++) {
          const a = t * (k % 2 ? -.5 : .65) + k * 2.1;
          const rr = .95 + .1 * Math.sin(t * 1.3 + k * 2);
          const [x, y, z] = p(Math.cos(a) * rr, Math.sin(a) * rr, .25 * Math.sin(t * .7 + k * 3));
          const tw = .5 + .5 * Math.sin(t * 3 + k * 2.4);
          dots.push({ x, y, z, r: (.6 + .9 * tw) * rs, v: .85, a: .25 + .6 * tw, c: k === 0 ? cBlue : k === 1 ? cPurple : cPink });
        }
        /* core glimmer */
        const [x0, y0, z0] = p(0, 0, 0);
        dots.push({ x: x0, y: y0, z: z0 + .01, r: (1.1 + .5 * Math.sin(t * 2.2)) * rs, v: .9, c: cPurple });
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ FIGMA — swatch morph ============ */
      const FIGMA_COLS = [
        [242, 78, 30],   /* L-top  */
        [255, 114, 98],  /* R-top  */
        [162, 89, 255],  /* L-mid  */
        [26, 188, 254],  /* R-mid  */
        [10, 207, 131]   /* L-bot  */
      ];
      const FIGMA_POS = [[-.21, -.42], [.21, -.42], [-.21, 0], [.21, 0], [-.21, .42]];
      function drawFigma(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .8;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const per = o.mini ? 6 : 13;       /* dots per swatch */
        const N = per * 5;
        /* cycle: sphere → logo → sphere */
        const T = 7, u = ((t * .9) % T + T) % T;
        let m; /* 0 = sphere, 1 = logo */
        if (u < 2.8) m = 0;
        else if (u < 3.7) m = smooth((u - 2.8) / .9);
        else if (u < 5.6) m = 1;
        else if (u < 6.5) m = 1 - smooth((u - 5.6) / .9);
        else m = 0;
        const p = proj(t * .5, .32 + .1 * Math.sin(t * .35), cx, cy, R);
        const dots = [];
        for (let i = 0; i < N; i++) {
          const grp = i % 5;
          const idx = (i / 5) | 0;
          /* sphere home */
          const f = fib(i, N);
          const [sx, sy, sz] = p(f[0], f[1], f[2]);
          /* logo home: tight sunflower disc per swatch, face-on */
          const ring = .155 * Math.sqrt((idx + .5) / per);
          const ang = idx * 2.399963 + grp * 1.2;
          const bob = .008 * Math.sin(t * 1.6 + grp * 1.3);
          const lx = cx + (FIGMA_POS[grp][0] + Math.cos(ang) * ring) * R * 1.05;
          const ly = cy + (FIGMA_POS[grp][1] + bob + Math.sin(ang) * ring) * R * 1.05;
          const x = lerp(sx, lx, m), y = lerp(sy, ly, m), z = lerp(sz, grp * .05 - .1, m);
          const dep = (z + 1) / 2;
          dots.push({
            x, y, z,
            r: (.8 + 1.4 * lerp(dep, .85, m)) * rs,
            v: lerp(.45 + .48 * dep, .85, m),
            c: FIGMA_COLS[grp]
          });
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ REACT — the atom ============ */
      function drawReact(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .92;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.1 * Math.sin(t * .4), .12 * Math.sin(t * .33), cx, cy, R);
        const spin = t * .26, rx = .94, ry = .345;
        const per = o.mini ? 20 : 56;
        const dots = [];
        for (let k = 0; k < 3; k++) {
          const a0 = spin + k * Math.PI / 3;
          const ca = Math.cos(a0), sa = Math.sin(a0);
          const ring = th => {
            const ex = Math.cos(th) * rx, ey = Math.sin(th) * ry;
            return [ex * ca - ey * sa, ex * sa + ey * ca];
          };
          for (let i = 0; i < per; i++) {
            const th = i / per * TAU;
            const [gx, gy] = ring(th);
            const [x, y, z] = p(gx, gy, 0);
            /* a highlight travels each orbit so the flat mark still breathes */
            const ph = ((th / TAU - t * .19 - k * .33) % 1 + 1) % 1;
            const crest = Math.exp(-Math.pow(ph - .5, 2) / .022);
            dots.push({ x, y, z: z + crest * .01, r: (.95 + .6 * crest) * rs, v: .66 + .3 * crest, a: .85 + .15 * crest });
          }
          const eth = t * (k % 2 ? -1.15 : 1.3) + k * 2.1;
          const [ex2, ey2] = ring(eth);
          const [x2, y2, z2] = p(ex2, ey2, .04);
          dots.push({ x: x2, y: y2, z: z2 + .02, r: 1.9 * rs, v: .95 });
        }
        /* nucleus */
        const nN = o.mini ? 3 : 7;
        for (let i = 0; i < nN; i++) {
          const a = i / nN * TAU, rr = i ? .085 : 0;
          const [x, y, z] = p(Math.cos(a) * rr, Math.sin(a) * rr, .05);
          dots.push({ x, y, z: z + .03, r: 1.5 * rs, v: .9 });
        }
        paint(ctx, dots, o.accent, .88, .3);
      }

      /* ============ SWIFT — the bird ============ */
      const OPENAI_PATH = "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z";
      const SWIFT_PATH = "M13.543 3.41c4.114 2.47 6.545 7.162 5.549 11.131-.024.093-.05.181-.076.272l.002.001c2.062 2.538 1.5 5.258 1.236 4.745-1.072-2.086-3.066-1.568-4.088-1.043a6.803 6.803 0 0 1-.281.158l-.02.012-.002.002c-2.115 1.123-4.957 1.205-7.812-.022a12.568 12.568 0 0 1-5.64-4.838c.649.48 1.35.902 2.097 1.252 3.019 1.414 6.051 1.311 8.197-.002C9.651 12.73 7.101 9.67 5.146 7.191a10.628 10.628 0 0 1-1.005-1.384c2.34 2.142 6.038 4.83 7.365 5.576C8.69 8.408 6.208 4.743 6.324 4.86c4.436 4.47 8.528 6.996 8.528 6.996.154.085.27.154.36.213.085-.215.16-.437.224-.668.708-2.588-.09-5.548-1.893-7.992z";
      const maskCache = new Map();
      /* sample a real logo path into a dot lattice, normalised on its own bounding box */
      function pathDots(key, d, N, vb, strokeW, inv, rc) {
        const ck = key + "-" + N + "-" + (inv || "") + (rc ? "-rc" : "");
        if (maskCache.has(ck)) return maskCache.get(ck);
        const px = 200, c = document.createElement("canvas");
        c.width = c.height = px;
        const g = c.getContext("2d");
        g.setTransform(px / (vb || 24), 0, 0, px / (vb || 24), 0, 0);
        if (strokeW) {
          g.strokeStyle = "#fff"; g.lineWidth = strokeW; g.lineJoin = "round"; g.lineCap = "round";
          g.stroke(new Path2D(d));
        } else {
          g.fillStyle = "#fff";
          g.fill(new Path2D(d));
        }
        const img = g.getImageData(0, 0, px, px).data;
        let x0 = px, x1 = -1, y0 = px, y1 = -1;
        for (let j = 0; j < px; j++) for (let i = 0; i < px; i++)
          if (img[(j * px + i) * 4 + 3] > 128) { if (i < x0) x0 = i; if (i > x1) x1 = i; if (j < y0) y0 = j; if (j > y1) y1 = j; }
        const mx = (x0 + x1) / 2, my = (y0 + y1) / 2, m = Math.max(x1 - x0, y1 - y0);
        const pts = [];
        for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
          const sx = mx + ((i + .5) / N * 2 - 1) * m / 2, sy = my + ((j + .5) / N * 2 - 1) * m / 2;
          const ix = Math.round(sx), iy = Math.round(sy);
          if (ix < 0 || iy < 0 || ix >= px || iy >= px) continue;
          const on = img[(iy * px + ix) * 4 + 3] > 128;
          const nx = (sx - mx) / (m / 2), ny = (sy - my) / (m / 2);
          if (inv) {
            /* the mark is the hole: keep empty pixels that sit inside the outer silhouette */
            if (on) continue;
            if (inv === "circle" && Math.hypot(nx, ny) > .96) continue;
            if (inv === "box" && Math.pow(Math.abs(nx), 4) + Math.pow(Math.abs(ny), 4) > Math.pow(.9, 4)) continue;
          } else if (!on) continue;
          pts.push([nx, ny]);
        }
        /* a mark carried as a hole is normalised against the outer silhouette, so it can sit
           off-centre in the frame; recentre it on its own bounds */
        if (rc && pts.length) {
          let ax0 = 1e9, ax1 = -1e9, ay0 = 1e9, ay1 = -1e9;
          for (const [qx, qy] of pts) {
            if (qx < ax0) ax0 = qx; if (qx > ax1) ax1 = qx;
            if (qy < ay0) ay0 = qy; if (qy > ay1) ay1 = qy;
          }
          const ox = (ax0 + ax1) / 2, oy = (ay0 + ay1) / 2;
          for (const q of pts) { q[0] -= ox; q[1] -= oy; }
        }
        maskCache.set(ck, pts);
        return pts;
      }

      /* ---------- marks sampled straight from each brand's own logo path ---------- */
      const MARK_PATHS = {
        github: "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
        x: "M14.234 10.162 22.977 0h-2.072l-7.591 8.824L7.251 0H.258l9.168 13.343L.258 24H2.33l8.016-9.318L16.749 24h6.993zm-2.837 3.299-.929-1.329L3.076 1.56h3.182l5.965 8.532.929 1.329 7.754 11.09h-3.182z",
        instagram: "M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077",
        threads: "M12.186 24h-.007c-3.581-.024-6.334-1.205-8.184-3.509C2.35 18.44 1.5 15.586 1.472 12.01v-.017c.03-3.579.879-6.43 2.525-8.482C5.845 1.205 8.6.024 12.18 0h.014c2.746.02 5.043.725 6.826 2.098 1.677 1.29 2.858 3.13 3.509 5.467l-2.04.569c-1.104-3.96-3.898-5.984-8.304-6.015-2.91.022-5.11.936-6.54 2.717C4.307 6.504 3.616 8.914 3.589 12c.027 3.086.718 5.496 2.057 7.164 1.43 1.783 3.631 2.698 6.54 2.717 2.623-.02 4.358-.631 5.8-2.045 1.647-1.613 1.618-3.593 1.09-4.798-.31-.71-.873-1.3-1.634-1.75-.192 1.352-.622 2.446-1.284 3.272-.886 1.102-2.14 1.704-3.73 1.79-1.202.065-2.361-.218-3.259-.801-1.063-.689-1.685-1.74-1.752-2.964-.065-1.19.408-2.285 1.33-3.082.88-.76 2.119-1.207 3.583-1.291a13.853 13.853 0 0 1 3.02.142c-.126-.742-.375-1.332-.75-1.757-.513-.586-1.308-.883-2.359-.89h-.029c-.844 0-1.992.232-2.721 1.32L7.734 7.847c.98-1.454 2.568-2.256 4.478-2.256h.044c3.194.02 5.097 1.975 5.287 5.388.108.046.216.094.321.142 1.49.7 2.58 1.761 3.154 3.07.797 1.82.871 4.79-1.548 7.158-1.85 1.81-4.094 2.628-7.277 2.65Zm1.003-11.69c-.242 0-.487.007-.739.021-1.836.103-2.98.946-2.916 2.143.067 1.256 1.452 1.839 2.784 1.767 1.224-.065 2.818-.543 3.086-3.71a10.5 10.5 0 0 0-2.215-.221z",
        linkedin: "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
        css: "M0 0v20.16A3.84 3.84 0 0 0 3.84 24h16.32A3.84 3.84 0 0 0 24 20.16V3.84A3.84 3.84 0 0 0 20.16 0Zm14.256 13.08c1.56 0 2.28 1.08 2.304 2.64h-1.608c.024-.288-.048-.6-.144-.84-.096-.192-.288-.264-.552-.264-.456 0-.696.264-.696.84-.024.576.288.888.768 1.08.72.288 1.608.744 1.92 1.296q.432.648.432 1.656c0 1.608-.912 2.592-2.496 2.592-1.656 0-2.4-1.032-2.424-2.688h1.68c0 .792.264 1.176.792 1.176.264 0 .456-.072.552-.24.192-.312.24-1.176-.048-1.512-.312-.408-.912-.6-1.32-.816q-.828-.396-1.224-.936c-.24-.36-.36-.888-.36-1.536 0-1.44.936-2.472 2.424-2.448m5.4 0c1.584 0 2.304 1.08 2.328 2.64h-1.608c0-.288-.048-.6-.168-.84-.096-.192-.264-.264-.528-.264-.48 0-.72.264-.72.84s.288.888.792 1.08c.696.288 1.608.744 1.92 1.296.264.432.408.984.408 1.656.024 1.608-.888 2.592-2.472 2.592-1.68 0-2.424-1.056-2.448-2.688h1.68c0 .744.264 1.176.792 1.176.264 0 .456-.072.552-.24.216-.312.264-1.176-.048-1.512-.288-.408-.888-.6-1.32-.816-.552-.264-.96-.576-1.2-.936s-.36-.888-.36-1.536c-.024-1.44.912-2.472 2.4-2.448m-11.031.018c.711-.006 1.419.198 1.839.63.432.432.672 1.128.648 1.992H9.336c.024-.456-.096-.792-.432-.96-.312-.144-.768-.048-.888.24-.12.264-.192.576-.168.864v3.504c0 .744.264 1.128.768 1.128a.65.65 0 0 0 .552-.264c.168-.24.192-.552.168-.84h1.776c.096 1.632-.984 2.712-2.568 2.688-1.536 0-2.496-.864-2.472-2.472v-4.032c0-.816.24-1.44.696-1.848.432-.408 1.146-.624 1.857-.63",
        ios: "M1.1 6.05C.486 6.05 0 6.53 0 7.13A1.08 1.08 0 0 0 1.1 8.21C1.72 8.21 2.21 7.73 2.21 7.13C2.21 6.53 1.72 6.05 1.1 6.05M8.71 6.07C5.35 6.07 3.25 8.36 3.25 12C3.25 15.67 5.35 17.95 8.71 17.95C12.05 17.95 14.16 15.67 14.16 12C14.16 8.36 12.05 6.07 8.71 6.07M19.55 6.07C17.05 6.07 15.27 7.45 15.27 9.5C15.27 11.13 16.28 12.15 18.4 12.64L19.89 13C21.34 13.33 21.93 13.81 21.93 14.64C21.93 15.6 20.96 16.28 19.58 16.28C18.17 16.28 17.11 15.59 17 14.53H15C15.08 16.65 16.82 17.95 19.46 17.95C22.25 17.95 24 16.58 24 14.4C24 12.69 23 11.72 20.68 11.19L19.35 10.89C17.94 10.55 17.36 10.1 17.36 9.34C17.36 8.38 18.24 7.74 19.54 7.74C20.85 7.74 21.75 8.39 21.85 9.46H23.81C23.76 7.44 22.09 6.07 19.55 6.07M8.71 7.82C10.75 7.82 12.06 9.45 12.06 12C12.06 14.57 10.75 16.2 8.71 16.2C6.65 16.2 5.35 14.57 5.35 12C5.35 9.45 6.65 7.82 8.71 7.82M.111 9.31V17.76H2.1V9.31H.11Z",
        neuform: "M111.571 49.9795L84 64.7156L112.332 77.9309 M107.889 87.5876L77.9727 78.5118L88.6616 107.89 M78.6897 111.575L63.9536 84.0035L50.7383 112.335 M41.0796 107.89L50.1554 77.9739L20.7773 88.6627 M17.0924 78.6912L44.6636 63.9551L16.332 50.7398 M20.7812 41.0833L50.697 50.1591L40.0081 20.781 M49.9766 17.0959L64.7127 44.6672L77.928 16.3356 M87.5875 20.7808L78.5117 50.6965L107.89 40.0077",
        designcode: "M14 12H24C29.5228 12 34 16.4772 34 22C34 27.5228 29.5228 32 24 32H14V12Z M30.3581 14.3347C28.6503 12.9333 26.6553 12.0237 24.2764 12L14.2469 22L24.2764 32C26.6552 31.9762 28.6503 31.041 30.3581 29.6397C30.3166 29.5982 27.6374 27.0121 26.6669 26.0446C25.6965 25.0772 23.2779 22.7255 22.5501 22C22.5501 22 30.3166 14.3762 30.3581 14.3347Z"
      };
      /* one driver for every sampled mark; each brand is just a config */
      function drawMark(ctx, S, t, o, cfg) {
        const cx = S / 2, cy = S / 2, R = S / 2 * (cfg.fit ?? .88);
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.15 * Math.sin(t * .4), .13 * Math.sin(t * .31), cx, cy, R);
        const pts = pathDots(cfg.key, MARK_PATHS[cfg.key], o.mini ? (cfg.nMini ?? 12) : (cfg.n ?? 26), cfg.vb, cfg.stroke, cfg.invert, cfg.recenter);
        const wave = (((t * (cfg.speed ?? .4)) % 1 + 1) % 1) * 2.4 - 1.2;
        const dots = [];
        for (const [gx, gy] of pts) {
          let crest;
          if (cfg.motion === "scan") crest = Math.exp(-Math.pow(gy - wave, 2) / .05);
          else if (cfg.motion === "sweep") {
            const ph = ((Math.atan2(gy, gx) / TAU + .5 - t * .3) % 1 + 1) % 1;
            crest = Math.exp(-Math.pow(ph - .5, 2) / .014);
          } else crest = Math.exp(-Math.pow((gx - gy) * .5 - wave, 2) / .05);
          const [x, y, z] = p(gx, -gy, 0);
          const dep = (z + 1) / 2;
          const d = { x, y, z, r: (.78 + .72 * dep + .45 * crest) * rs, v: (cfg.v ?? .58) + .15 * dep + .3 * crest };
          if (cfg.grad) {
            const m = clamp01((gy + 1) / 2);
            d.c = [lerp(cfg.grad[0][0], cfg.grad[1][0], m),
            lerp(cfg.grad[0][1], cfg.grad[1][1], m),
            lerp(cfg.grad[0][2], cfg.grad[1][2], m)];
          }
          dots.push(d);
        }
        paint(ctx, dots, cfg.accent ?? null, cfg.accent ? .9 : 0, .3);
      }
      const mk = cfg => (ctx, S, t, o) => drawMark(ctx, S, t, o, cfg);

      /* walk a real path at uniform arc length, so its lines come out as even dot runs */
      const walkCache = new Map();
      function pathWalk(key, d, spacing, ox, oy, sc) {
        const ck = "w" + key + "-" + spacing;
        if (walkCache.has(ck)) return walkCache.get(ck);
        const NS = "http://www.w3.org/2000/svg";
        const svg = document.createElementNS(NS, "svg");
        svg.setAttribute("width", "0");
        svg.setAttribute("height", "0");
        svg.style.cssText = "position:absolute;left:-9999px;top:0";
        document.body.appendChild(svg);
        const pts = [];
        for (const sub of d.split(/(?=M)/)) {          /* every subpath gets its own even queue */
          if (!sub.trim()) continue;
          const el = document.createElementNS(NS, "path");
          el.setAttribute("d", sub);
          svg.appendChild(el);
          const L = el.getTotalLength();
          if (!L) continue;
          const n = Math.max(2, Math.round(L / spacing));
          for (let i = 0; i < n; i++) {
            const q = el.getPointAtLength((i + .5) / n * L);
            pts.push([(q.x - ox) * sc, (q.y - oy) * sc]);
          }
        }
        svg.remove();
        walkCache.set(ck, pts);
        return pts;
      }

      /* ============ DESIGNCODE — monogram in a dot field ============ */
      /* geometry is static, so build it once per size: the disc, minus a clearance
         around the monogram, plus the monogram itself. Normalised on the logo's own
         disc (centre 22,22 r 22 of its 44 viewBox) so the proportions are the logo's. */
      const dcCache = new Map();
      function dcGeom(mini) {
        const ck = mini ? "m" : "s";
        if (dcCache.has(ck)) return dcCache.get(ck);
        /* the monogram, walked evenly along its own outlines (logo's disc: centre 22,22 r 22 of 44) */
        const mark = pathWalk("designcode", MARK_PATHS.designcode, mini ? 3.1 : 1.5, 22, 22, 1 / 22);
        /* the disc of dots behind it, kept clear of the lines */
        const fg = mini ? .26 : .12, cl = mini ? .17 : .105, cl2 = cl * cl;
        const field = [];
        for (let gy = -1; gy <= 1; gy += fg) {
          for (let gx = -1; gx <= 1; gx += fg) {
            if (Math.hypot(gx, gy) > .97) continue;
            let near = false;
            for (const [mx2, my2] of mark) {
              const dx = gx - mx2, dy = gy - my2;
              if (dx * dx + dy * dy < cl2) { near = true; break; }
            }
            if (!near) field.push([gx, gy]);
          }
        }
        const geom = { mark, field };
        dcCache.set(ck, geom);
        return geom;
      }
      function drawDesignCode(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .82;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.12 * Math.sin(t * .38), .12 * Math.sin(t * .29), cx, cy, R);
        const { mark, field } = dcGeom(o.mini);
        const wave = (((t * .3) % 1 + 1) % 1) * 2.3 - 1.15;
        const dots = [];
        for (const [gx, gy] of field) {
          const [x, y, z] = p(gx, -gy, 0);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (.7 + .58 * dep) * rs, v: .3 + .1 * dep, a: .82 });
        }
        for (const [gx, gy] of mark) {
          const crest = Math.exp(-Math.pow(gy - wave, 2) / .06);
          const [x, y, z] = p(gx, -gy, .05);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (.9 + .75 * dep + .3 * crest) * rs, v: .78 + .1 * dep + .18 * crest });
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ AURA — the logo's own dot field ============ */
      /* [x, y, radius] for each circle in the Aura mark, normalised on its bounding box */
      const AURA_DOTS = [[-0.173, -0.959, 0.065], [-0.015, -0.963, 0.061], [0.138, -0.971, 0.052], [-0.264, -0.803, 0.059], [-0.103, -0.804, 0.058], [0.056, -0.807, 0.055], [0.207, -0.817, 0.044], [-0.336, -0.636, 0.064], [-0.172, -0.634, 0.067], [-0.012, -0.636, 0.064], [0.131, -0.655, 0.045], [0.284, -0.664, 0.036], [-0.417, -0.47, 0.068], [-0.291, -0.507, 0.032], [-0.143, -0.52, 0.018], [0.049, -0.49, 0.048], [0.201, -0.5, 0.038], [0.357, -0.506, 0.033], [-0.499, -0.313, 0.064], [-0.375, -0.351, 0.025], [-0.217, -0.355, 0.021], [0.131, -0.331, 0.045], [0.285, -0.339, 0.037], [0.439, -0.346, 0.03], [-0.589, -0.157, 0.058], [-0.456, -0.185, 0.03], [-0.298, -0.19, 0.025], [0.207, -0.17, 0.045], [0.361, -0.178, 0.036], [0.513, -0.187, 0.027], [-0.669, 0.002, 0.055], [-0.534, -0.024, 0.029], [0.291, -0.009, 0.043], [0.45, -0.012, 0.041], [0.598, -0.026, 0.026], [-0.755, 0.163, 0.054], [-0.611, 0.146, 0.036], [-0.457, 0.137, 0.028], [0.36, 0.145, 0.035], [0.523, 0.146, 0.036], [0.675, 0.136, 0.026], [-0.836, 0.322, 0.05], [-0.681, 0.315, 0.043], [-0.524, 0.31, 0.039], [-0.355, 0.316, 0.045], [-0.196, 0.314, 0.043], [-0.038, 0.31, 0.038], [0.117, 0.303, 0.032], [0.265, 0.289, 0.018], [0.442, 0.304, 0.032], [0.601, 0.301, 0.03], [0.759, 0.297, 0.025], [-0.924, 0.48, 0.047], [-0.765, 0.477, 0.044], [-0.588, 0.492, 0.058], [-0.43, 0.488, 0.055], [-0.3, 0.456, 0.023], [-0.118, 0.476, 0.043], [0.035, 0.468, 0.035], [0.197, 0.467, 0.034], [0.353, 0.462, 0.028], [0.516, 0.463, 0.029], [0.677, 0.462, 0.029], [0.832, 0.455, 0.022], [-1.0, 0.643, 0.048], [-0.839, 0.642, 0.047], [-0.675, 0.645, 0.05], [-0.527, 0.631, 0.035], [0.123, 0.632, 0.037], [0.277, 0.625, 0.029], [0.437, 0.623, 0.028], [0.599, 0.623, 0.028], [0.757, 0.619, 0.024], [0.918, 0.618, 0.023], [-0.92, 0.808, 0.051], [-0.762, 0.804, 0.047], [0.357, 0.79, 0.033], [0.517, 0.787, 0.03], [0.676, 0.785, 0.028], [0.835, 0.782, 0.024], [1.0, 0.785, 0.028], [-0.995, 0.971, 0.053], [-0.835, 0.97, 0.051], [0.604, 0.951, 0.033], [0.761, 0.947, 0.028], [0.926, 0.95, 0.031]];
      function drawAura(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .63;
        const rs = rscale(S) * (o.mini ? 1.7 : 1);
        const p = proj(.14 * Math.sin(t * .36), .12 * Math.sin(t * .28), cx, cy, R);
        /* an aura travels outward through the field */
        const ring = (((t * .32) % 1 + 1) % 1) * 2.2 - .2;
        const dots = [];
        const step = o.mini ? 2 : 1;
        for (let i = 0; i < AURA_DOTS.length; i += step) {
          const [gx, gy, gr] = AURA_DOTS[i];
          const d0 = Math.hypot(gx, gy);
          const glow = Math.exp(-Math.pow(d0 - ring, 2) / .045);
          const [x, y, z] = p(gx, -gy, 0);
          const dep = (z + 1) / 2;
          dots.push({
            x, y, z,
            r: Math.max(.4, gr * R * .92) + (.25 * dep + .5 * glow) * rs,
            v: .5 + .12 * dep + .36 * glow
          });
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ FLOWER (study) — tapered petal bloom ============ */
      function drawFlower(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .92;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.12 * Math.sin(t * .34), .12 * Math.sin(t * .27), cx, cy, R);
        const petals = 6, spin = t * .15;
        const open = .9 + .1 * Math.sin(t * .8);           /* the bloom breathes */
        const a = .42, b = .335;                           /* petal half-length / half-width */
        const mid = .53 * open;                            /* petal centre, measured from the middle */
        const gap = o.mini ? .17 : .076;
        const dots = [];
        for (let k = 0; k < petals; k++) {
          const th = spin + k / petals * TAU;
          const ca = Math.cos(th), sa = Math.sin(th);
          const lean = .5 + .5 * Math.sin(t * .9 + k * 1.05);
          for (let u = -a; u <= a; u += gap) {
            /* teardrop: pinched toward the centre, full at the outer end */
            const bw = b * (.5 + .5 * (u + a) / (2 * a));
            for (let v = -bw; v <= bw; v += gap) {
              const q = Math.pow(Math.abs(u / a), 2.8) + Math.pow(Math.abs(v / bw), 2.4);
              if (q > 1) continue;
              const rad = mid + u;
              const gx = rad * ca - v * sa, gy = rad * sa + v * ca;
              const [x, y, z] = p(gx, -gy, .05 * (1 - q));
              const dep = (z + 1) / 2;
              const rim = clamp01(q);
              dots.push({
                x, y, z,
                r: (.68 + .6 * dep + .3 * rim) * rs,
                v: .48 + .13 * dep + .26 * rim + .1 * lean,
                a: .7 + .24 * rim
              });
            }
          }
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ DREAMCUT — the blossom ============ */
      function drawDreamCut(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .88;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.11 * Math.sin(t * .33), .11 * Math.sin(t * .26), cx, cy, R);
        const petals = 6, spin = t * .14;
        const breathe = 1 + .04 * Math.sin(t * .9);
        /* six round lobes, spaced so they overlap into a scalloped blossom */
        const d = .46 * breathe, rp = .41 * breathe, hole = .11;
        const pc = [];
        for (let k = 0; k < petals; k++) {
          const th = spin + k / petals * TAU;
          pc.push([Math.cos(th) * d, Math.sin(th) * d]);
        }
        const gap = o.mini ? .2 : .1;
        const glow = (((t * .3) % 1 + 1) % 1) * TAU;      /* a highlight travels round the bloom */
        const dots = [];
        const lit = (gx, gy) => .5 + .5 * Math.cos(Math.atan2(gy, gx) - glow);
        /* dim fill: the union of the six lobes */
        for (let gy = -1; gy <= 1; gy += gap) {
          for (let gx = -1; gx <= 1; gx += gap) {
            if (Math.hypot(gx, gy) < hole) continue;       /* the dark centre */
            let bd = 9;
            for (let k = 0; k < petals; k++) {
              const dd = Math.hypot(gx - pc[k][0], gy - pc[k][1]);
              if (dd < bd) bd = dd;
            }
            if (bd > rp) continue;
            const [x, y, z] = p(gx, -gy, .03);
            const dep = (z + 1) / 2;
            const l = lit(gx, gy);
            dots.push({ x, y, z, r: (.58 + .45 * dep) * rs, v: .27 + .09 * dep + .15 * l * l, a: .66 });
          }
        }
        /* each petal's own edge, so the six lobes read as petals and not one blob */
        const per = o.mini ? 10 : 26;
        for (let k = 0; k < petals; k++) {
          for (let i = 0; i < per; i++) {
            const a = i / per * TAU;
            const gx = pc[k][0] + Math.cos(a) * rp, gy = pc[k][1] + Math.sin(a) * rp;
            if (Math.hypot(gx, gy) < hole) continue;
            const [x, y, z] = p(gx, -gy, .06);
            const dep = (z + 1) / 2;
            const l = lit(gx, gy);
            dots.push({ x, y, z, r: (.88 + .78 * dep) * rs, v: .66 + .12 * dep + .26 * l * l });
          }
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ EMAIL — the envelope, flap lifting ============ */
      function drawEmail(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .8;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.14 * Math.sin(t * .4), .14 * Math.sin(t * .3), cx, cy, R);
        /* gy runs downward here, so -h is the top edge */
        const w = .88, h = .6, r = .24;
        /* opens, holds, shuts again */
        const cyc = ((t * .3) % 1 + 1) % 1;
        const lift = smooth(Math.sin(clamp01(cyc * 1.5) * Math.PI));
        /* the letter only shows once the flap has actually lifted */
        const show = clamp01((lift - .2) / .3);
        const step = o.mini ? .28 : .128;                 /* spaced like the cube's edges */
        const dots = [];
        /* one dot, cube-weighted: bigger and brighter as it comes forward */
        const dot = (gx, gy, z0, v, mul) => {
          const [x, y, z] = p(gx, -gy, z0 || 0);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (.82 + 1.5 * dep) * rs, v: v + .44 * dep, a: (.62 + .38 * dep) * (mul ?? 1) });
        };
        const node = (gx, gy, z0, mul) => {              /* the cube's brighter corner anchors */
          const [x, y, z] = p(gx, -gy, z0 || 0);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (1.22 + 1.5 * dep) * rs, v: .62 + .4 * dep, a: (.68 + .32 * dep) * (mul ?? 1) });
        };
        const line = (ax, ay, bx, by, v, z0, mul) => {
          const L = Math.hypot(bx - ax, by - ay), n = Math.max(2, Math.round(L / step));
          for (let i = 0; i <= n; i++) {
            const f = i / n;
            dot(ax + (bx - ax) * f, ay + (by - ay) * f, z0, v, mul);
          }
        };
        /* rounded envelope body, walked at even spacing */
        const body = [];
        const arc = (ax, ay, a0, a1) => {
          for (let i = 0; i <= 5; i++) {
            const a = a0 + (a1 - a0) * i / 5;
            body.push([ax + Math.cos(a) * r, ay + Math.sin(a) * r]);
          }
        };
        body.push([-w + r, -h], [w - r, -h]);
        arc(w - r, -h + r, -Math.PI / 2, 0);
        body.push([w, h - r]);
        arc(w - r, h - r, 0, Math.PI / 2);
        body.push([-w + r, h]);
        arc(-w + r, h - r, Math.PI / 2, Math.PI);
        body.push([-w, -h + r]);
        arc(-w + r, -h + r, Math.PI, Math.PI * 1.5);
        let per = 0;
        for (let i = 0; i < body.length; i++) {
          const a = body[i], b = body[(i + 1) % body.length];
          per += Math.hypot(b[0] - a[0], b[1] - a[1]);
        }
        const bodyPath = perimeter(body);
        const N = Math.max(8, Math.round(per / step));
        for (let i = 0; i < N; i++) {
          const [gx, gy] = bodyPath((i + .5) / N);
          dot(gx, gy, 0, .5);
        }
        /* anchors where the four corners turn */
        const kx = w - r * .3, ky = h - r * .3;
        node(-kx, -ky); node(kx, -ky); node(kx, ky); node(-kx, ky);
        /* the letter: hidden while shut, rising into view as the flap opens */
        if (show > .02) {
          const lw = w * .6, lh = h * .62, lr = .1, lz = -.06;
          const ly = 0;                                 /* sits centred; the flap does the revealing */
          line(-lw + lr, ly - lh, lw - lr, ly - lh, .56, lz, show);
          line(-lw + lr, ly + lh, lw - lr, ly + lh, .56, lz, show);
          line(-lw, ly - lh + lr, -lw, ly + lh - lr, .56, lz, show);
          line(lw, ly - lh + lr, lw, ly + lh - lr, .56, lz, show);
          if (!o.mini) {                                  /* a couple of written lines */
            line(-lw * .55, ly - lh * .3, lw * .55, ly - lh * .3, .5, lz, show);
            line(-lw * .55, ly + lh * .12, lw * .28, ly + lh * .12, .5, lz, show);
          }
          node(-lw, ly - lh, lz, show); node(lw, ly - lh, lz, show);
        }
        /* the flap: creased along the top edge, dipping in when shut, swinging up when open */
        const apex = lerp(.34 * h, -1.5 * h, lift);
        const fx = w - r * .4, fy = -h + r * .1;
        line(-fx, fy, 0, apex, .6, .07);
        line(fx, fy, 0, apex, .6, .07);
        node(0, apex, .08);
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ OPENAI — the rosette, blooming ============ */
      function drawOpenAI(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .9;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.12 * Math.sin(t * .38), .12 * Math.sin(t * .29), cx, cy, R);
        const pts = pathDots("openai", OPENAI_PATH, o.mini ? 14 : 34);
        /* furls shut and opens again; the outer petals swirl further than the middle */
        const cyc = ((t * .28) % 1 + 1) % 1;
        const open = smooth(Math.sin(cyc * Math.PI));
        const scl = .5 + .5 * open;
        const dots = [];
        for (const [gx0, gy0] of pts) {
          const r0 = Math.hypot(gx0, gy0), th = Math.atan2(gy0, gx0);
          const a = th + (1 - open) * 1.5 * r0 + t * .1;
          const rr = r0 * scl;
          const [x, y, z] = p(Math.cos(a) * rr, -Math.sin(a) * rr, 0);
          const dep = (z + 1) / 2;
          dots.push({
            x, y, z,
            r: (.78 + .7 * dep + .4 * r0 * open) * rs,
            v: .5 + .16 * dep + .28 * r0 * open
          });
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ NEUFORM — eight chevrons ============ */
      function drawNeuform(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .88;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.13 * Math.sin(t * .36), .12 * Math.sin(t * .28), cx, cy, R);
        /* the mark is drawn in strokes, so walk it evenly rather than sampling a fill */
        const pts = pathWalk("neuform", MARK_PATHS.neuform, o.mini ? 6.5 : 2.9, 64, 64, 1 / 64);
        const spin = t * .12, cs = Math.cos(spin), sn = Math.sin(spin);
        /* light pushes outward through the eight arms */
        const wave = (((t * .34) % 1 + 1) % 1) * 1.55 - .1;
        const dots = [];
        for (const [gx0, gy0] of pts) {
          const gx = gx0 * cs - gy0 * sn, gy = gx0 * sn + gy0 * cs;
          const rr = Math.hypot(gx, gy);
          const crest = Math.exp(-Math.pow(rr - wave, 2) / .035);
          const [x, y, z] = p(gx, -gy, 0);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (.8 + .7 * dep + .55 * crest) * rs, v: .48 + .14 * dep + .34 * crest });
        }
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ UI — the panel ============ */
      function drawUI(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .84;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.15 * Math.sin(t * .34), .14 * Math.sin(t * .27), cx, cy, R);
        const step = o.mini ? .3 : .13;
        const dots = [];
        const dot = (gx, gy, v, mul) => {
          const [x, y, z] = p(gx, -gy, 0);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (.8 + 1.45 * dep) * rs, v: v + .42 * dep, a: (.6 + .4 * dep) * (mul ?? 1) });
        };
        const line = (ax, ay, bx, by, v, mul) => {
          const L = Math.hypot(bx - ax, by - ay), n = Math.max(2, Math.round(L / step));
          for (let i = 0; i <= n; i++) {
            const f = i / n;
            dot(ax + (bx - ax) * f, ay + (by - ay) * f, v, mul);
          }
        };
        const w = .84, h = .64, r = .16, bar = -h + .3, side = -w + .42;
        /* the window frame */
        line(-w + r, -h, w - r, -h, .5); line(-w + r, h, w - r, h, .5);
        line(-w, -h + r, -w, h - r, .5); line(w, -h + r, w, h - r, .5);
        for (const [ax, ay, a0] of [[w - r, -h + r, -Math.PI / 2], [w - r, h - r, 0], [-w + r, h - r, Math.PI / 2], [-w + r, -h + r, Math.PI]])
          for (let i = 0; i <= 4; i++) {
            const a = a0 + i / 4 * (Math.PI / 2);
            dot(ax + Math.cos(a) * r, ay + Math.sin(a) * r, .5);
          }
        line(-w, bar, w, bar, .46);                      /* title bar */
        line(side, bar, side, h, .42);                   /* sidebar */
        if (!o.mini) { dot(-w + .17, -h + .15, .8); dot(-w + .3, -h + .15, .8); }
        /* content rows light up in turn, like a panel filling in */
        const rows = o.mini ? 2 : 3;
        for (let i = 0; i < rows; i++) {
          const yy = bar + .22 + i * .24;
          const pulse = .5 + .5 * Math.sin(t * 1.5 - i * 1.1);
          line(side + .16, yy, w - .16 - (i === rows - 1 ? .28 : 0), yy, .36 + .3 * pulse);
        }
        /* and a nav item on the sidebar */
        if (!o.mini) for (let i = 0; i < 2; i++) {
          const yy = bar + .28 + i * .3;
          line(-w + .14, yy, side - .12, yy, .34 + .22 * (.5 + .5 * Math.sin(t * 1.5 - i * 1.1 - .6)));
        }
        paint(ctx, dots, o.accent, .86, .3);
      }

      /* ============ UX — the journey ============ */
      const uxCurve = u => [-.82 + 1.64 * u, .40 * Math.cos(u * Math.PI) - .17 * Math.sin(u * TAU)];
      function drawUX(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .86;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.15 * Math.sin(t * .33), .14 * Math.sin(t * .26), cx, cy, R);
        const dots = [];
        const dot = (gx, gy, v, size, mul) => {
          const [x, y, z] = p(gx, -gy, 0);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: ((size ?? .8) + 1.4 * dep) * rs, v: v + .4 * dep, a: (.6 + .4 * dep) * (mul ?? 1) });
        };
        /* the path itself, evenly spaced */
        const N = o.mini ? 13 : 34;
        for (let i = 0; i <= N; i++) {
          const u = i / N, q = uxCurve(u);
          /* a traveller runs the route */
          const head = (((t * .32) % 1 + 1) % 1);
          const d = Math.abs(u - head);
          const crest = Math.exp(-d * d / .006);
          dot(q[0], q[1], .38 + .38 * crest, .78 + .5 * crest);
        }
        /* waypoints along the way */
        for (const u of (o.mini ? [.5] : [.06, .5, .94])) {
          const q = uxCurve(u);
          const ring = o.mini ? 5 : 9, rr = .13;
          for (let i = 0; i < ring; i++) {
            const a = i / ring * TAU;
            dot(q[0] + Math.cos(a) * rr, q[1] + Math.sin(a) * rr, .58, .78);
          }
        }
        /* an arrowhead where the route ends */
        if (!o.mini) {
          const e = uxCurve(1), b = uxCurve(.93);
          const ang = Math.atan2(e[1] - b[1], e[0] - b[0]);
          for (const s2 of [-1, 1]) for (let i = 1; i <= 3; i++) {
            const a = ang + Math.PI + s2 * .62, f = i / 3 * .2;
            dot(e[0] + Math.cos(a) * f, e[1] + Math.sin(a) * f, .66);
          }
        }
        paint(ctx, dots, o.accent, .86, .3);
      }

      /* ============ CODEX — prompt blob ============ */
      const CODEX_CHEV = [[-.30, -.34], [.07, 0], [-.30, .34]];   /* the '>' , y down */
      const CODEX_BAR = [[.11, .30], [.43, .30]];                 /* the '_' */
      function segDist(px, py, ax, ay, bx, by) {
        const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy;
        let u = L2 ? ((px - ax) * dx + (py - ay) * dy) / L2 : 0;
        u = u < 0 ? 0 : u > 1 ? 1 : u;
        return Math.hypot(px - (ax + dx * u), py - (ay + dy * u));
      }
      function drawCodex(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .92;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(.13 * Math.sin(t * .42), .13 * Math.sin(t * .31), cx, cy, R);
        const lobes = 6, spin = t * .2;
        const amp = .1 + .03 * Math.sin(t * 1.15);
        const rad = th => .76 * (1 + amp * Math.cos(lobes * (th - spin)));
        /* the underscore blinks like a terminal caret */
        const ph = ((t / 1.15) % 1 + 1) % 1;
        const blink = ph < .58 ? 1 : ph < .68 ? 1 - (ph - .58) / .1 : ph < .9 ? 0 : (ph - .9) / .1;
        const light = [186, 186, 252], deep = [104, 96, 246];
        const dots = [];
        const gap = o.mini ? .28 : .112;
        const clr = o.mini ? .1 : .108;
        const chevD = (x, y) => Math.min(
          segDist(x, y, CODEX_CHEV[0][0], CODEX_CHEV[0][1], CODEX_CHEV[1][0], CODEX_CHEV[1][1]),
          segDist(x, y, CODEX_CHEV[1][0], CODEX_CHEV[1][1], CODEX_CHEV[2][0], CODEX_CHEV[2][1]));
        const barD = (x, y) => segDist(x, y, CODEX_BAR[0][0], CODEX_BAR[0][1], CODEX_BAR[1][0], CODEX_BAR[1][1]);
        for (let gy = -1; gy <= 1; gy += gap) {
          for (let gx = -1; gx <= 1; gx += gap) {
            const d = Math.hypot(gx, gy);
            if (!d || d > rad(Math.atan2(gy, gx))) continue;
            if (chevD(gx, gy) < clr || barD(gx, gy) < clr * .92) continue;   /* leave room for the glyphs */
            const [x, y, z] = p(gx, -gy, 0);
            const dep = (z + 1) / 2, m = clamp01((gy + .85) / 1.7);
            dots.push({
              x, y, z, r: (.9 + 1.05 * dep) * rs, a: .95,
              v: .8 - .12 * m,
              c: [lerp(light[0], deep[0], m), lerp(light[1], deep[1], m), lerp(light[2], deep[2], m)]
            });
          }
        }
        /* the prompt itself, in white */
        const step = o.mini ? .13 : .052;
        const glyph = (ax, ay, bx, by, alpha) => {
          const L = Math.hypot(bx - ax, by - ay), n = Math.max(2, Math.round(L / step));
          for (let i = 0; i <= n; i++) {
            const f = i / n, gx = ax + (bx - ax) * f, gy = ay + (by - ay) * f;
            const [x, y, z] = p(gx, -gy, .06);
            dots.push({ x, y, z, r: (1.15 + 1.1 * ((z + 1) / 2)) * rs, v: .97, a: alpha, c: [255, 255, 255] });
          }
        };
        glyph(CODEX_CHEV[0][0], CODEX_CHEV[0][1], CODEX_CHEV[1][0], CODEX_CHEV[1][1], 1);
        glyph(CODEX_CHEV[1][0], CODEX_CHEV[1][1], CODEX_CHEV[2][0], CODEX_CHEV[2][1], 1);
        if (blink > .02) glyph(CODEX_BAR[0][0], CODEX_BAR[0][1], CODEX_BAR[1][0], CODEX_BAR[1][1], blink);
        paint(ctx, dots, null, 0, .3);
      }

      /* ============ SWIFT — the bird ============ */
      function drawSwift(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .88;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        /* a slow bank, as if riding an updraft */
        const p = proj(.2 * Math.sin(t * .43), .18 * Math.sin(t * .31) - .04, cx, cy, R);
        const pts = pathDots("swift", SWIFT_PATH, o.mini ? 11 : 27);
        const bob = .035 * Math.sin(t * .95);
        const wave = (((t * .4) % 1 + 1) % 1) * 2.4 - 1.2;
        const dots = [];
        for (const [gx, gy] of pts) {
          /* crest sweeps tail-to-beak along the bird's diagonal */
          const u = (gx - gy) * .5;
          const crest = Math.exp(-Math.pow(u - wave, 2) / .05);
          const [x, y, z] = p(gx, -gy + bob, 0);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (.75 + .8 * dep + .45 * crest) * rs, v: .6 + .16 * dep + .26 * crest });
        }
        paint(ctx, dots, o.accent, .92, .3);
      }

      /* ============ FRAMER — letter morph ============ */
      const FRAMER_PTS = (() => {
        /* dot fill of the logo's three sections; each one carries its own diagonal (viewBox 24) */
        const pts = [], g = 1.72;
        for (let y = .9; y <= 7.4; y += g)                    /* top: left edge runs down to (12,8) */
          for (let x = 4 + y; x <= 19.4; x += g) pts.push([x, y, 0]);
        for (let y = 8.9; y <= 15.4; y += g)                  /* middle: right edge runs out to (20,16) */
          for (let x = 4.9; x <= 12 + (y - 8); x += g) pts.push([x, y, 1]);
        for (let y = 16.9; y <= 23.4; y += g)                 /* bottom: left edge runs down to (12,24) */
          for (let x = 4 + (y - 16); x <= 11.9; x += g) pts.push([x, y, 2]);
        return pts;
      })();
      function drawFramer(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .8;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const list = o.mini ? FRAMER_PTS.filter((_, i) => i % 2 === 0) : FRAMER_PTS;
        const N = list.length;
        /* cycle: sphere -> letter -> sphere (phase-shifted against the Figma orb) */
        const T = 7, u = (((t * .9 + 3.5) % T) + T) % T;
        let m;
        if (u < 2.8) m = 0;
        else if (u < 3.7) m = smooth((u - 2.8) / .9);
        else if (u < 5.6) m = 1;
        else if (u < 6.5) m = 1 - smooth((u - 5.6) / .9);
        else m = 0;
        const p = proj(t * .5, .32 + .1 * Math.sin(t * .35), cx, cy, R);
        const dots = [];
        for (let i = 0; i < N; i++) {
          const [lx0, ly0, sec] = list[i];
          const f = fib(i, N);
          const [sx, sy, sz] = p(f[0], f[1], f[2]);
          const sway = .012 * Math.sin(t * 1.4 + sec * 2.1) * (sec === 1 ? -1 : 1);
          const lx = cx + ((lx0 - 12) / 12 * .95 + sway) * R * 1.02;
          const ly = cy + ((ly0 - 12) / 12 * .95) * R * 1.02;
          const x = lerp(sx, lx, m), y = lerp(sy, ly, m), z = lerp(sz, sec * .05 - .08, m);
          const dep = (z + 1) / 2;
          dots.push({
            x, y, z,
            r: (.8 + 1.35 * lerp(dep, .85, m)) * rs,
            v: lerp(.42 + .48 * dep, .87, m)
          });
        }
        paint(ctx, dots, o.accent, .9, .3);
      }

      /* ============ BLUE ORB (study) — band shift ============ */
      function drawBands(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .8;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        const p = proj(t * .08, .35, cx, cy, R);
        const perRing = o.mini ? 14 : 22;
        const bands = [-.58, 0, .58];
        const sub = o.mini ? [0] : [-.09, 0, .09];
        /* eased 90-degree snap every few beats, alternating direction per band */
        const beat = 2.4, w = t / beat, step = Math.floor(w), f = w - step;
        const snapped = step + smooth(clamp01(f * 2.2));
        const snapPulse = Math.sin(clamp01(f * 2.2) * Math.PI);
        const dots = [];
        for (let b = 0; b < 3; b++) {
          const dir = b % 2 ? -1 : 1;
          const phase = dir * (snapped * Math.PI / 2 + t * .18) + b * .8;
          const hot = (step % 3 === b ? 1 : .25) * snapPulse;
          for (const so of sub) {
            const yy = bands[b] + so;
            const rad = Math.sqrt(Math.max(0, 1 - yy * yy)) * .96;
            for (let j = 0; j < perRing; j++) {
              const th = j / perRing * TAU + phase;
              const [x, y, z] = p(Math.cos(th) * rad, yy, Math.sin(th) * rad);
              const dep = (z + 1) / 2;
              dots.push({
                x, y, z,
                r: (.7 + 1.5 * dep + .45 * hot) * rs,
                v: .4 + .48 * dep + .16 * hot,
                a: .45 + .55 * dep
              });
            }
          }
        }
        paint(ctx, dots, o.accent, .9, .3);
      }

      /* ============ BOOK COVERS (study) — a closed book with a mark stamped on it ============ */
      /* the mark is laid onto the cover plane, so it takes the book's perspective */
      function drawBookCover(ctx, S, t, o, cfg) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .9;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        /* a gentle three-quarter that drifts, so the cover turns through the light */
        const yaw = .55 + .13 * Math.sin(t * .28);
        const p = proj(yaw, .34 + .06 * Math.sin(t * .41), cx, cy, R);
        const w = .54, h = .72, d = .15;          /* half width / height / half thickness */
        const gapE = o.mini ? .33 : .155;         /* the cube's dot step */
        const dots = [];
        const dot = (gx, gy, gz, v, mul, col) => {
          const [x, y, z] = p(gx, gy, gz);
          const dep = (z + 1) / 2;
          const q = { x, y, z, r: (.8 + 1.5 * dep) * rs, v: v + .44 * dep, a: (.58 + .42 * dep) * (mul ?? 1) };
          if (col) q.c = col;
          dots.push(q);
        };
        const node = (gx, gy, gz, mul) => {
          const [x, y, z] = p(gx, gy, gz);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (1.2 + 1.5 * dep) * rs, v: .52 + .4 * dep, a: (.62 + .38 * dep) * (mul ?? 1) });
        };
        const edge = (a, b, v, mul) => {
          const L = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
          const k = Math.max(2, Math.round(L / gapE));
          for (let i = 0; i < k; i++) {
            const f = (i + .5) / k;
            dot(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, v, mul);
          }
        };
        /* the closed slab */
        const V = [];
        for (const sx of [-w, w]) for (const sy of [-h, h]) for (const sz of [-d, d]) V.push([sx, sy, sz]);
        const ix = (a, b, c) => (a ? 4 : 0) + (b ? 2 : 0) + (c ? 1 : 0);
        const E = [];
        for (const a of [0, 1]) for (const b of [0, 1]) E.push([ix(a, b, 0), ix(a, b, 1)]);
        for (const a of [0, 1]) for (const c of [0, 1]) E.push([ix(a, 0, c), ix(a, 1, c)]);
        for (const b of [0, 1]) for (const c of [0, 1]) E.push([ix(0, b, c), ix(1, b, c)]);
        for (const [i, j] of E) edge(V[i], V[j], .45);
        for (const q of V) node(q[0], q[1], q[2]);
        /* page edges along the fore-edge, away from the spine */
        if (!o.mini) for (const pz of [-d * .5, 0, d * .5])
          edge([w, -h * .9, pz], [w, h * .9, pz], .34);
        /* the mark, stamped on the front cover */
        const front = d + .02, sp = w * .78;
        /* as the book turns, a highlight rakes across the cover */
        for (const [u, v, weight, col] of cfg.marks(t, o)) {
          const rake = .55 + .45 * Math.cos(u * 2.1 - yaw * 3.4);
          dot(u * sp, -v * sp, front, (cfg.base ?? .5) * weight + .26 * weight * rake, 1, col || cfg.col);
        }
        paint(ctx, dots, null, 0, .3);
      }
      /* Claude's spark burst, flattened onto the cover */
      const claudeCoverMarks = (t, o) => {
        const out = [], rays = o.mini ? 8 : 11, per = o.mini ? 3 : 5;
        for (let k = 0; k < rays; k++) {
          const a = k / rays * TAU + t * .1 + (hash(k, 3.1) - .5) * .28;
          const pulse = .5 + .5 * Math.sin(t * 1.7 - k * 1.13);
          const L = (.6 + .38 * hash(k, 7.7)) * (.82 + .24 * pulse * pulse);
          for (let j = 0; j < per; j++) {
            const f = (j + .8) / per;
            out.push([Math.cos(a) * L * f, Math.sin(a) * L * f, .62 + .3 * f + .2 * pulse]);
          }
        }
        out.push([0, 0, 1.25]);
        return out;
      };
      /* OpenAI's rosette, stamped still like a foil block */
      const openaiCoverMarks = (t, o) => {
        const pts = pathDots("openai", OPENAI_PATH, o.mini ? 10 : 17);
        const breathe = 1 + .02 * Math.sin(t * .8);
        return pts.map(([gx, gy]) => [gx * .78 * breathe, gy * .78 * breathe, .9]);
      };

      /* ---- 2-D mark geometry for the book covers: still stamps, built once and cached ---- */
      const coverCache = new Map();
      const cov = (key, build) => {
        if (!coverCache.has(key)) coverCache.set(key, build());
        return coverCache.get(key);
      };
      /* lay dots along a segment */
      const covSeg = (out, ax, ay, bx, by, step, w, col) => {
        const L = Math.hypot(bx - ax, by - ay), n = Math.max(2, Math.round(L / step));
        for (let i = 0; i <= n; i++) {
          const f = i / n;
          out.push([ax + (bx - ax) * f, ay + (by - ay) * f, w, col]);
        }
      };
      /* sample a real logo path straight onto the cover */
      const covPath = (key, d, N, sc, vb, stroke, inv, rc) =>
        pathDots("cov" + key, d, N, vb, stroke, inv, rc).map(([x, y]) => [x * sc, y * sc, .92]);

      const COVER_MARKS = {
        openai: () => cov("openai", () => covPath("openai", OPENAI_PATH, 17, .78)),
        swift: () => cov("swift", () => covPath("swift", SWIFT_PATH, 16, .8)),
        github: () => cov("github", () => covPath("github", MARK_PATHS.github, 18, .8, 24, 0, "circle", 1)),
        linkedin: () => cov("linkedin", () => covPath("linkedin", MARK_PATHS.linkedin, 18, .76, 24, 0, "box", 1)),
        x: () => cov("x", () => covPath("x", MARK_PATHS.x, 16, .72)),
        instagram: () => cov("instagram", () => covPath("instagram", MARK_PATHS.instagram, 17, .78)),
        threads: () => cov("threads", () => covPath("threads", MARK_PATHS.threads, 17, .78)),
        designcode: () => cov("designcode", () =>
          pathWalk("dcCover", MARK_PATHS.designcode, 1.9, 22, 22, 1 / 22).map(([x, y]) => [x * 1.55, y * 1.55, .95])),
        framer: () => cov("framer", () =>
          FRAMER_PTS.map(([x, y]) => [(x - 12) / 12 * .78, (y - 12) / 12 * .78, .92])),
        aura: () => cov("aura", () =>
          AURA_DOTS.map(([x, y, r]) => [x * .82, y * .82, .6 + 5 * r])),
        css: () => cov("css", () => covPath("css", MARK_PATHS.css, 19, .8, 24, 0, "box", 1)),
        ios: () => cov("ios", () => covPath("ios", MARK_PATHS.ios, 20, .86)),
        neuform: () => cov("neuform", () =>
          pathWalk("nfCover", MARK_PATHS.neuform, 3.1, 64, 64, 1 / 64).map(([x, y]) => [x * .84, y * .84, .95])),
        ui: () => cov("ui", () => {
          const o = [], w = .74, h = .56, bar = -h + .26, side = -w + .36;
          covSeg(o, -w, -h, w, -h, .1, .92); covSeg(o, w, -h, w, h, .1, .92);
          covSeg(o, w, h, -w, h, .1, .92); covSeg(o, -w, h, -w, -h, .1, .92);
          covSeg(o, -w, bar, w, bar, .1, .9);
          covSeg(o, side, bar, side, h, .1, .86);
          for (let i = 0; i < 3; i++) covSeg(o, side + .14, bar + .2 + i * .2, w - .14, bar + .2 + i * .2, .1, .8);
          return o;
        }),
        ux: () => cov("ux", () => {
          const o = [];
          for (let i = 0; i <= 30; i++) { const q = uxCurve(i / 30); o.push([q[0] * .82, q[1] * .82, .9]); }
          for (const u of [.06, .5, .94]) {
            const q = uxCurve(u);
            for (let i = 0; i < 9; i++) {
              const a = i / 9 * TAU;
              o.push([(q[0] + Math.cos(a) * .13) * .82, (q[1] + Math.sin(a) * .13) * .82, 1]);
            }
          }
          return o;
        }),
        codex: () => cov("codex", () => {
          const o = [];
          covSeg(o, -.4, -.44, .1, 0, .075, .95);          /* the '>' */
          covSeg(o, .1, 0, -.4, .44, .075, .95);
          covSeg(o, .17, .4, .62, .4, .075, .95);          /* the '_' */
          return o;
        }),
        cursor: () => cov("cursor", () => {
          const o = [], P = ARROW_CLEAN;
          for (let i = 0; i < P.length; i++) {
            const a = P[i], b = P[(i + 1) % P.length];
            covSeg(o, a[0] * .58, a[1] * .58, b[0] * .58, b[1] * .58, .07, .95);
          }
          return o;
        }),
        gemini: () => cov("gemini", () => {
          const o = [], N = 44;
          for (let i = 0; i < N; i++) {
            const th = i / N * TAU, c = Math.cos(th), sn = Math.sin(th);
            o.push([c * c * c * .82, sn * sn * sn * .82, .95]);
          }
          return o;
        }),
        figma: () => cov("figma", () => {
          const o = [];
          FIGMA_POS.forEach(([px, py], g) => {
            for (let i = 0; i < 15; i++) {
              const ring = .175 * Math.sqrt((i + .5) / 15), a = i * 2.399963 + g * 1.2;
              o.push([px * 1.62 + Math.cos(a) * ring, py * 1.62 + Math.sin(a) * ring, .98, FIGMA_COLS[g]]);
            }
          });
          return o;
        }),
        react: () => cov("react", () => {
          const o = [], rx = .84, ry = .3, per = 26;
          for (let k = 0; k < 3; k++) {
            const a0 = k * Math.PI / 3, ca = Math.cos(a0), sa = Math.sin(a0);
            for (let i = 0; i < per; i++) {
              const th = i / per * TAU, ex = Math.cos(th) * rx, ey = Math.sin(th) * ry;
              o.push([ex * ca - ey * sa, ex * sa + ey * ca, .9]);
            }
          }
          o.push([0, 0, 1.15]);
          return o;
        }),
        dreamcut: () => cov("dreamcut", () => {
          const o = [], petals = 6, d = .44, rp = .39, hole = .1;
          const pc = [];
          for (let k = 0; k < petals; k++) {
            const th = k / petals * TAU;
            pc.push([Math.cos(th) * d, Math.sin(th) * d]);
          }
          for (let gy = -.9; gy <= .9; gy += .135) {          /* dim fill */
            for (let gx = -.9; gx <= .9; gx += .135) {
              if (Math.hypot(gx, gy) < hole) continue;
              let bd = 9;
              for (const q of pc) { const dd = Math.hypot(gx - q[0], gy - q[1]); if (dd < bd) bd = dd; }
              if (bd > rp) continue;
              o.push([gx, gy, .58]);
            }
          }
          for (const q of pc) {                                /* each petal's own edge */
            for (let i = 0; i < 24; i++) {
              const a = i / 24 * TAU;
              const px = q[0] + Math.cos(a) * rp, py = q[1] + Math.sin(a) * rp;
              if (Math.hypot(px, py) < hole) continue;
              o.push([px, py, 1]);
            }
          }
          return o;
        }),
        email: () => cov("email", () => {
          const o = [], w = .74, h = .5;
          covSeg(o, -w, -h, w, -h, .085, .92);
          covSeg(o, w, -h, w, h, .085, .92);
          covSeg(o, w, h, -w, h, .085, .92);
          covSeg(o, -w, h, -w, -h, .085, .92);
          covSeg(o, -w, -h, 0, h * .34, .085, .95);        /* the flap */
          covSeg(o, w, -h, 0, h * .34, .085, .95);
          return o;
        })
      };
      const COVER_COL = {
        css: [156, 116, 224], ios: [214, 214, 224], ui: [130, 200, 240], ux: [240, 190, 120],
        claude: [222, 132, 100], codex: [176, 176, 250], gemini: [186, 132, 246],
        framer: [80, 140, 255], react: [120, 224, 250], swift: [242, 118, 88],
        designcode: [180, 224, 238], instagram: [228, 118, 156], linkedin: [80, 148, 226]
      };
      /* one book per mark */
      const bookOf = key => (c, S, t, o) => drawBookCover(c, S, t, o, {
        marks: key === "claude" ? claudeCoverMarks
          : key === "openai" ? openaiCoverMarks
            : (tt, oo) => COVER_MARKS[key](tt, oo),
        col: COVER_COL[key],
        base: .5
      });

      /* ============ BOOK (study) — open book, cube-style wireframe ============ */
      function drawBook(ctx, S, t, o) {
        const cx = S / 2, cy = S / 2, R = S / 2 * .84;
        const rs = rscale(S) * (o.mini ? 1.8 : 1);
        /* a three-quarter view like the cube's, drifting */
        const p = proj(.4 + .14 * Math.sin(t * .28), .66 + .05 * Math.sin(t * .44), cx, cy, R);
        const h = .58, Lp = .92;                   /* page half-height / page width, sized so edges carry the cube's dot count */
        /* the cube spaces 8 dots along a 1.24 edge; match that step so every line here is even */
        const gapE = o.mini ? .33 : .155;
        const dots = [];
        const dot = (gx, gy, gz, v, mul) => {
          const [x, y, z] = p(gx, gy, gz);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (.8 + 1.5 * dep) * rs, v: v + .44 * dep, a: (.55 + .45 * dep) * (mul ?? 1) });
        };
        const node = (gx, gy, gz, mul) => {        /* the cube's brighter corner anchors */
          const [x, y, z] = p(gx, gy, gz);
          const dep = (z + 1) / 2;
          dots.push({ x, y, z, r: (1.2 + 1.5 * dep) * rs, v: .52 + .4 * dep, a: (.6 + .4 * dep) * (mul ?? 1) });
        };
        const edge = (a, b, v, mul) => {
          const L = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
          const k = Math.max(2, Math.round(L / gapE));   /* count follows length, so spacing stays constant */
          for (let i = 0; i < k; i++) {
            const f = (i + .5) / k;
            dot(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, v, mul);
          }
        };
        /* the two halves breathe between flat-open and tented */
        const lift = .17 + .19 * (.5 + .5 * Math.sin(t * .5));
        /* one half, standing off the spine at angle th (measured in the x-z plane) */
        const leaf = (th, v, mul) => {
          const ex = Math.cos(th) * Lp, ez = Math.sin(th) * Lp;
          edge([0, -h, 0], [ex, -h, ez], v, mul);
          edge([ex, -h, ez], [ex, h, ez], v, mul);
          edge([ex, h, ez], [0, h, 0], v, mul);
          node(ex, -h, ez, mul);
          node(ex, h, ez, mul);
        };
        leaf(lift, .42);                            /* right half */
        leaf(Math.PI - lift, .42);                  /* left half */
        /* the spine, and its anchors */
        edge([0, -h, 0], [0, h, 0], .6);
        node(0, -h, 0); node(0, h, 0);
        /* page edges stacked on each half */
        if (!o.mini) for (const f of [.4, .64, .86]) {
          for (const th of [lift, Math.PI - lift]) {
            const ex = Math.cos(th) * Lp * f, ez = Math.sin(th) * Lp * f;
            edge([ex, -h * .93, ez], [ex, h * .93, ez], .32);
          }
        }
        /* now and then a page sweeps over from one side to the other */
        const cyc = ((t * .24) % 1 + 1) % 1;
        if (cyc < .5) {
          const tau = smooth(cyc / .5);
          const th = lerp(lift, Math.PI - lift, tau);
          const fade = Math.sin(tau * Math.PI) * .55 + .45;
          leaf(th, .66, fade);
        }
        paint(ctx, dots, null, 0, .3);
      }

      const MODES = {
        claude: { draw: drawClaude, accent: [217, 119, 87], speed: 1, staticT: 1.4 },
        openai: { draw: drawOpenAI, accent: null, speed: 1, staticT: .8 },
        cursor: { draw: drawCursor, accent: null, speed: 1, staticT: 1 },
        gemini: { draw: drawGemini, accent: null, speed: 1, staticT: .9 },
        figma: { draw: drawFigma, accent: null, speed: 1, staticT: 5 },
        framer: { draw: drawFramer, accent: [51, 119, 255], speed: 1, staticT: 1.1 },
        codex: { draw: drawCodex, accent: null, speed: 1, staticT: .4 },
        react: { draw: drawReact, accent: [97, 218, 251], speed: 1, staticT: 1.2 },
        sphere: { draw: drawSphere, accent: null, speed: 1, staticT: .8 },
        css: { draw: mk({ key: "css", n: 30, nMini: 13, motion: "scan", speed: .34, invert: "box", accent: [150, 110, 220], v: .66, fit: 1.02 }), accent: null, speed: 1, staticT: 1.2 },
        ios: { draw: mk({ key: "ios", n: 30, nMini: 13, motion: "diag", fit: .78, v: .64 }), accent: null, speed: 1, staticT: 1.1 },
        neuform: { draw: drawNeuform, accent: null, speed: 1, staticT: 1.5 },
        ui: { draw: drawUI, accent: [130, 200, 240], speed: 1, staticT: 1.2 },
        ux: { draw: drawUX, accent: [240, 190, 120], speed: 1, staticT: 1.6 },
        designcode: { draw: drawDesignCode, accent: null, speed: 1, staticT: 1.3 },
        aura: { draw: drawAura, accent: null, speed: 1, staticT: 1.5 },
        dreamcut: { draw: drawDreamCut, accent: null, speed: 1, staticT: 1.2 },
        swift: { draw: drawSwift, accent: [240, 81, 56], speed: 1, staticT: .9 },
        github: { draw: mk({ key: "github", n: 30, nMini: 13, motion: "diag", invert: "circle", recenter: true, v: .62 }), accent: null, speed: 1, staticT: 1.1 },
        x: { draw: mk({ key: "x", n: 30, nMini: 12, motion: "sweep", fit: .70, v: .64 }), accent: null, speed: 1, staticT: 1.1 },
        instagram: {
          draw: mk({
            key: "instagram", n: 28, nMini: 13, motion: "sweep", fit: .74,
            grad: [[151, 78, 200], [250, 140, 70]], v: .68
          }), accent: null, speed: 1, staticT: 1.4
        },
        threads: { draw: mk({ key: "threads", n: 30, nMini: 13, motion: "sweep", fit: .74, v: .64 }), accent: null, speed: 1, staticT: 1.2 },
        linkedin: { draw: mk({ key: "linkedin", n: 30, nMini: 13, motion: "scan", speed: .38, invert: "box", accent: [40, 130, 220], v: .66 }), accent: null, speed: 1, staticT: 1.2 },
        email: { draw: drawEmail, accent: null, speed: 1, staticT: 1.2 },
        flower: { draw: drawFlower, accent: null, speed: 1, staticT: 1.2 },
        book: { draw: drawBook, accent: null, speed: 1, staticT: .52 },
        claudebook: { draw: bookOf("claude"), accent: null, speed: 1, staticT: 1.3 },
        openaibook: { draw: bookOf("openai"), accent: null, speed: 1, staticT: 1.3 },
        codexbook: { draw: bookOf("codex"), accent: null, speed: 1, staticT: 1.3 },
        cursorbook: { draw: bookOf("cursor"), accent: null, speed: 1, staticT: 1.3 },
        geminibook: { draw: bookOf("gemini"), accent: null, speed: 1, staticT: 1.3 },
        figmabook: { draw: bookOf("figma"), accent: null, speed: 1, staticT: 1.3 },
        framerbook: { draw: bookOf("framer"), accent: null, speed: 1, staticT: 1.3 },
        reactbook: { draw: bookOf("react"), accent: null, speed: 1, staticT: 1.3 },
        swiftbook: { draw: bookOf("swift"), accent: null, speed: 1, staticT: 1.3 },
        designcodebook: { draw: bookOf("designcode"), accent: null, speed: 1, staticT: 1.3 },
        aurabook: { draw: bookOf("aura"), accent: null, speed: 1, staticT: 1.3 },
        dreamcutbook: { draw: bookOf("dreamcut"), accent: null, speed: 1, staticT: 1.3 },
        githubbook: { draw: bookOf("github"), accent: null, speed: 1, staticT: 1.3 },
        xbook: { draw: bookOf("x"), accent: null, speed: 1, staticT: 1.3 },
        instagrambook: { draw: bookOf("instagram"), accent: null, speed: 1, staticT: 1.3 },
        threadsbook: { draw: bookOf("threads"), accent: null, speed: 1, staticT: 1.3 },
        linkedinbook: { draw: bookOf("linkedin"), accent: null, speed: 1, staticT: 1.3 },
        emailbook: { draw: bookOf("email"), accent: null, speed: 1, staticT: 1.3 },
        uibook: { draw: bookOf("ui"), accent: null, speed: 1, staticT: 1.3 },
        uxbook: { draw: bookOf("ux"), accent: null, speed: 1, staticT: 1.3 },
        cssbook: { draw: bookOf("css"), accent: null, speed: 1, staticT: 1.3 },
        iosbook: { draw: bookOf("ios"), accent: null, speed: 1, staticT: 1.3 },
        neuformbook: { draw: bookOf("neuform"), accent: null, speed: 1, staticT: 1.3 },
        cube: { draw: drawCube, accent: null, speed: 1, staticT: 2.6 },
        orb: { draw: drawBands, accent: [64, 122, 255], speed: 1, staticT: .5 },
        pointer: { draw: drawPointer, accent: null, speed: 1, staticT: 1 }
      };
      window.BRAND_ORB_MODES = MODES;
    })();

    var MODES = window.BRAND_ORB_MODES;
    var ORB_MODES = [
      "claude", "openai", "codex", "cursor",
      "gemini", "react", "swift", "figma",
      "framer", "aura", "dreamcut", "designcode"
    ];

    var DUR = 26;
    var DW = 2962, DH = 2160, DASP = DW / DH;
    var RING = { a: 790, ratio: 0.825, axis: 25.5, n: 12, tile: 440, radius: 0.22, dist: 13, phase: 93 };

    function mkc(w, h) {
      var c = document.createElement("canvas");
      c.width = w; c.height = h;
      return c;
    }

    var TS = 512;
    var tileCanvases = [];
    for (var ti = 0; ti < 12; ti++) {
      tileCanvases.push(mkc(TS, TS));
    }

    var A_CIRCLES = `[[218.8,49.8,16.1],[252.8,49,15.1],[285.7,47.2,12.9],[199.2,83.4,14.6],[233.9,83.1,14.3],[268,82.5,13.6],[300.5,80.3,10.9],[183.8,119.3,15.8],[219,119.7,16.6],[253.4,119.3,15.8],[284.2,115.2,11.1],[317.1,113.2,8.9],[166.3,154.9,16.8],[193.4,147,7.9],[225.3,144.2,4.5],[266.5,150.7,11.9],[299.2,148.5,9.4],[332.8,147.2,8.2],[148.7,188.7,15.8],[175.4,180.5,6.2],[209.3,179.7,5.2],[284.2,184.8,11.1],[317.3,183.1,9.1],[350.4,181.6,7.4],[129.4,222.2,14.3],[158,216.2,7.4],[191.9,215.2,6.2],[300.5,219.4,11.1],[333.6,217.7,8.9],[366.3,215.8,6.7],[112.2,256.4,13.6],[141.2,250.8,7.2],[318.6,254.1,10.6],[352.8,253.4,10.1],[384.6,250.4,6.4],[93.7,291,13.4],[124.6,287.4,8.9],[157.7,285.5,6.9],[333.4,287.2,8.7],[368.4,287.4,8.9],[401.1,285.2,6.4],[76.3,325.2,12.4],[109.6,323.7,10.6],[143.3,322.6,9.6],[179.7,323.9,11.1],[213.9,323.5,10.6],[247.8,322.6,9.4],[281.2,321.1,7.9],[313,318.1,4.5],[351,321.4,7.9],[385.2,320.7,7.4],[419.2,319.9,6.2],[57.3,359.2,11.6],[91.5,358.6,10.9],[129.6,361.8,14.3],[163.6,360.9,13.6],[191.5,354,5.7],[230.6,358.3,10.6],[263.5,356.6,8.7],[298.4,356.4,8.4],[331.9,355.3,6.9],[366.9,355.5,7.2],[401.6,355.3,7.2],[434.9,353.8,5.4],[41,394.2,11.9],[75.6,394,11.6],[110.9,394.7,12.4],[142.7,391.7,8.7],[282.4,391.9,9.1],[315.6,390.4,7.2],[350,389.9,6.9],[384.8,389.9,6.9],[418.8,389.1,5.9],[453.4,388.9,5.7],[58.2,429.7,12.6],[92.2,428.9,11.6],[332.8,425.9,8.2],[367.2,425.2,7.4],[401.3,424.8,6.9],[435.5,424.1,5.9],[471,424.8,6.9],[42.1,464.8,13.1],[76.5,464.5,12.6],[385.9,460.5,8.2],[419.6,459.6,6.9],[455.1,460.2,7.7]]`;
    var parsedCircles = JSON.parse(A_CIRCLES);

    function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
    function seg(t, a, b) { return clamp((t - a) / (b - a), 0, 1); }
    function smooth(v) { return v * v * (3 - 2 * v); }
    function eOut(t) { return 1 - Math.pow(1 - t, 3); }
    function lerp(a, b, m) { return a + (b - a) * m; }
    function rng(seed) {
      var s = seed;
      return function () {
        s = (s * 9301 + 49297) % 233280;
        return s / 233280;
      };
    }

    var R_JIT = rng(7719);
    var WORD_STR = "ssembly";
    var JIT_OFFSETS = [];
    for (var ji = 0; ji < WORD_STR.length; ji++) {
      JIT_OFFSETS.push([R_JIT() * 2 - 1, R_JIT() * 2 - 1, R_JIT()]);
    }


    var ax = RING.axis * Math.PI / 180, cf = RING.ratio, sf = Math.sqrt(1 - cf * cf);
    var U = [Math.cos(ax), Math.sin(ax), 0];
    var V = [-Math.sin(ax) * cf, Math.cos(ax) * cf, sf];
    var AXIS = [
      U[1] * V[2] - U[2] * V[1],
      U[2] * V[0] - U[0] * V[2],
      U[0] * V[1] - U[1] * V[0]
    ];

    const cv = canvas, ctx = cv.getContext("2d");
    var W = 0, H = 0, K = 1, OX = 0, OY = 0;
    var charWidths = [];
    var charOffsets = [];
    var measuredTextW = 0;

    function d2sx(x) { return OX + x * K; }
    function d2sy(y) { return OY + y * K; }

    function measureTypography() {
      if (!W || !H) return;
      var fontSize = Math.round(315 * K);
      ctx.font = "700 " + fontSize + "px -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', sans-serif";
      charWidths = [];
      charOffsets = [];
      measuredTextW = 0;
      for (var i = 0; i < WORD_STR.length; i++) {
        charOffsets.push(measuredTextW);
        var cw = ctx.measureText(WORD_STR[i]).width;
        charWidths.push(cw);
        measuredTextW += cw;
      }
    }

    function drawHead(x, t, shiftY) {
      if (!W || !H) return;
      var fontSize = Math.round(315 * K);
      x.font = "700 " + fontSize + "px -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', sans-serif";
      x.textBaseline = "middle";

      var markSize = fontSize * 0.88;
      var gap = fontSize * 0.08;
      var totalW = markSize + gap + measuredTextW;

      var cx = d2sx(1481);
      var cy = d2sy(1080) + shiftY;
      var startX = cx - totalW / 2;

      var p = Math.min(1, t / 2.3);

      // 1. Draw animated popping Halftone Dotted A mark
      var mkO = smooth(seg(p, 0.2, 0.75));
      var mkS = lerp(0.5, 1, eOut(seg(p, 0.2, 0.8)));
      if (mkO > 0.01) {
        x.save();
        x.globalAlpha = mkO;
        x.shadowColor = "rgba(255, 255, 255, 0.9)";
        x.shadowBlur = fontSize * 0.16;
        var mkCenterX = startX + markSize / 2;
        var mkCenterY = cy;
        x.translate(mkCenterX, mkCenterY);
        x.scale(mkS, mkS);
        x.translate(-markSize / 2, -markSize / 2);

        x.fillStyle = "#ffffff";
        var sc = markSize / 512;
        for (var ci = 0; ci < parsedCircles.length; ci++) {
          var c = parsedCircles[ci];
          x.beginPath();
          x.arc(c[0] * sc, c[1] * sc, c[2] * sc, 0, Math.PI * 2);
          x.fill();
        }
        x.restore();
      }

      // 2. Draw animated assembling Assembly characters with chromatic RGB splits
      var textBaseX = startX + markSize + gap;
      for (var i = 0; i < WORD_STR.length; i++) {
        var j = JIT_OFFSETS[i];
        var a = eOut(clamp(seg(p, 0.04, 0.82) * 1.35 - j[2] * 0.35, 0, 1));
        var op = Math.min(1, a * 1.5);
        if (op < 0.02) continue;

        var sc = lerp(1.24, 1, a);
        var chX = textBaseX + charOffsets[i] + j[0] * 62 * (1 - a) * K;
        var chY = cy + j[1] * 34 * (1 - a) * K;
        var sep = (1 - a) * 14 * K;

        if (sep > 0.4) {
          // Chromatic RGB aberration splits
          x.save();
          x.globalAlpha = op * 0.85;
          x.fillStyle = "rgba(255, 64, 72, 0.85)";
          x.fillText(WORD_STR[i], chX - sep, chY);

          x.fillStyle = "rgba(64, 255, 190, 0.8)";
          x.fillText(WORD_STR[i], chX + sep, chY);

          x.fillStyle = "rgba(96, 124, 255, 0.8)";
          x.fillText(WORD_STR[i], chX, chY + sep * 0.55);
          x.restore();
        }

        // Main white character
        x.save();
        x.globalAlpha = op;
        x.fillStyle = "#ffffff";
        x.fillText(WORD_STR[i], chX, chY);
        x.restore();
      }
    }
    function project(p) {
      var x = p[0], y = p[1], z = p[2];
      var d = RING.dist, zp = d - z;
      var pers = d / Math.max(0.1, zp);
      return [d2sx(1481 + x * RING.a * pers), d2sy(1080 - y * RING.a * pers)];
    }

    function drawTile(i, psi) {
      var c = Math.cos(psi), s = Math.sin(psi);
      var C = [c * U[0] + s * V[0], c * U[1] + s * V[1], c * U[2] + s * V[2]];
      var T = [-s * U[0] + c * V[0], -s * U[1] + c * V[1], -s * U[2] + c * V[2]];
      var h = RING.tile / (2 * RING.a);
      var p0 = project(C);
      var pT = project([C[0] + T[0] * h, C[1] + T[1] * h, C[2] + T[2] * h]);
      var pA = project([C[0] + AXIS[0] * h, C[1] + AXIS[1] * h, C[2] + AXIS[2] * h]);
      var ex = pT[0] - p0[0], ey = pT[1] - p0[1];
      var fx = pA[0] - p0[0], fy = pA[1] - p0[1];
      if (Math.abs(ex * fy - ey * fx) < 0.4) return;

      var tc = tileCanvases[i % 12];
      ctx.save();
      ctx.setTransform(ex * 2 / TS, ey * 2 / TS, fx * 2 / TS, fy * 2 / TS, p0[0], p0[1]);

      // Pure glowing brand logo with genuine ThreeUI mathematical particle engine
      ctx.drawImage(tc, -TS / 2, -TS / 2, TS, TS);
      ctx.restore();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }

    function updateOrbs(tNow) {
      for (var k = 0; k < 12; k++) {
        var tc = tileCanvases[k], tx = tc.getContext("2d");
        tx.clearRect(0, 0, TS, TS);
        var modeName = ORB_MODES[k];
        var mode = MODES[modeName];
        if (mode && mode.draw) {
          mode.draw(tx, TS, tNow * mode.speed, { mini: false, accent: mode.accent });
        }
      }
    }

    function render(t, introT) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.imageSmoothingQuality = "high";

      updateOrbs(t);

  // Centered dead-center in the orbit ring
  var currentShiftY = 0;

      var spin = (t / DUR) * Math.PI * 2;
      var list = [], i;
      for (i = 0; i < RING.n; i++) {
        var psi = RING.phase * Math.PI / 180 - i * 2 * Math.PI / RING.n + spin;
        var c = Math.cos(psi), s = Math.sin(psi);
        list.push({ i: i, psi: psi, z: c * U[2] + s * V[2] });
      }
      list.sort(function (a, b) { return a.z - b.z; });

      // Wordmark drawn underneath orbiting logos so logos cleanly pass OVER 'A As' and 'bly'
      drawHead(ctx, introT, currentShiftY);

      for (i = 0; i < list.length; i++) {
        drawTile(list[i].i, list[i].psi);
      }
    }
    function resize() {
      var dpr = Math.min(2, window.devicePixelRatio || 1);
      const parentRect = cv.parentElement ? cv.parentElement.getBoundingClientRect() : null;
      const displayW = parentRect && parentRect.width > 0 ? Math.round(parentRect.width) : 660;
      const displayH = parentRect && parentRect.height > 0 ? Math.round(parentRect.height) : 580;
      const targetW = Math.round(displayW * dpr);
      const targetH = Math.round(displayH * dpr);

      // Guard: do not clear canvas buffer if dimensions have not changed (prevents flicker on scroll)
      if (W === targetW && H === targetH && cv.style.width === displayW + "px" && cv.style.height === displayH + "px") {
        return;
      }

      W = cv.width = targetW;
      H = cv.height = targetH;
      cv.style.width = displayW + "px";
      cv.style.height = displayH + "px";

      var S = Math.min(W, H * DASP);
      K = (S / DW) * 1.65;
      OX = (W - DW * K) / 2;
      OY = (H - DH * K) / 2;
      measureTypography();
    }

    var tNow = 0, playing = true;
    var introT = 3.6, introActive = true, introCompleted = true;
    var last = performance.now();

    function playIntro() {
      if (introActive || introCompleted) return;
      introT = 0;
      introActive = true;
    }

    function resetIntro() {
      if (introCompleted) return;
      introT = 0;
      introActive = false;
    }

    window.addEventListener("message", function (e) {
      if (e.data && (e.data.playIntro || e.data.type === "playIntro")) {
        playIntro();
      }
      if (e.data && (e.data.resetIntro || e.data.type === "resetIntro")) {
        resetIntro();
      }
    });

    try {
      window.parent?.postMessage({ type: "headingReady" }, "*");
    } catch { }

    function frame(now) {
      if (playing) {
        var dt = (now - last) / 1000;
        tNow += dt;
        if (introActive) {
          introT += dt;
          if (introT >= 3.6) {
            introT = 3.6;
            introCompleted = true;
            introActive = false;
          }
        }
      }
      last = now;
      render(tNow, introCompleted ? 3.6 : introT);
      animId = requestAnimationFrame(frame);
    }

    const onResize = function () { if (isDisposed) return; resize(); render(tNow, introT); }; window.addEventListener("resize", onResize);
    resize();
    render(tNow, introT);
    animId = requestAnimationFrame(frame);

  return () => {
    isDisposed = true;
    if (animId) cancelAnimationFrame(animId);
    if (typeof onResize === "function") {
      window.removeEventListener("resize", onResize);
    }
  };
}
