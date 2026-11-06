import { describe, it, expect } from "vitest";
import {
  HandSmoother,
  HandTracker,
  createOneEuroFilter,
  skinConfidence,
  type HandDetection,
} from "./hand-tracker";

const WIDTH = 128;
const HEIGHT = 96;
const SKIN: [number, number, number] = [200, 150, 120];

function blankFrame(): Uint8ClampedArray {
  const data = new Uint8ClampedArray(WIDTH * HEIGHT * 4);
  for (let index = 0; index < data.length; index += 4) {
    data[index] = 128;
    data[index + 1] = 128;
    data[index + 2] = 128;
    data[index + 3] = 255;
  }
  return data;
}

function paint(
  data: Uint8ClampedArray,
  x0: number,
  y0: number,
  w: number,
  h: number,
  color: [number, number, number] = SKIN,
) {
  for (let y = y0; y < y0 + h; y += 1) {
    for (let x = x0; x < x0 + w; x += 1) {
      const offset = (y * WIDTH + x) * 4;
      data[offset] = color[0];
      data[offset + 1] = color[1];
      data[offset + 2] = color[2];
      data[offset + 3] = 255;
    }
  }
}

function missingHand(): HandDetection {
  return {
    present: false,
    x: 0.5,
    y: 0.5,
    size: 0,
    fill: 0,
    motion: 0,
    confidence: 0,
    area: 0,
  };
}

function hand(overrides: Partial<HandDetection> = {}): HandDetection {
  return {
    present: true,
    x: 0.5,
    y: 0.6,
    size: 0.25,
    fill: 0.5,
    motion: 0.2,
    confidence: 0.7,
    area: 40,
    ...overrides,
  };
}

describe("skinConfidence", () => {
  it("accepts a range of warm skin tones", () => {
    expect(skinConfidence(230, 180, 150)).toBeGreaterThan(0.5);
    expect(skinConfidence(200, 150, 120)).toBeGreaterThan(0.5);
    expect(skinConfidence(140, 95, 70)).toBeGreaterThan(0.4);
    expect(skinConfidence(90, 60, 45)).toBeGreaterThan(0.3);
  });

  it("rejects neutral, blue, green, and near-black pixels", () => {
    expect(skinConfidence(128, 128, 128)).toBe(0);
    expect(skinConfidence(40, 90, 200)).toBe(0);
    expect(skinConfidence(60, 170, 70)).toBe(0);
    expect(skinConfidence(20, 20, 20)).toBe(0);
    expect(skinConfidence(245, 248, 250)).toBe(0);
  });
});

describe("createOneEuroFilter", () => {
  it("converges quickly to a step change without overshooting wildly", () => {
    const filter = createOneEuroFilter(1.4, 0.05);
    let value = 0;
    for (let index = 0; index < 10; index += 1) {
      value = filter(0, index * 16);
    }
    expect(value).toBeCloseTo(0, 5);

    for (let index = 10; index < 40; index += 1) {
      value = filter(1, index * 16);
    }
    expect(value).toBeGreaterThan(0.9);
    expect(value).toBeLessThanOrEqual(1.02);
  });

  it("resets back to the first sample", () => {
    const filter = createOneEuroFilter(1.4, 0.05);
    filter(5, 0);
    filter(5, 16);
    filter.reset();
    expect(filter(0.25, 32)).toBeCloseTo(0.25, 5);
  });
});

describe("HandTracker", () => {
  it("reports no hand for a plain frame", () => {
    const tracker = new HandTracker();
    const result = tracker.process(blankFrame(), WIDTH, HEIGHT, 0);
    expect(result.present).toBe(false);
    expect(result.confidence).toBe(0);
  });

  it("finds a skin-coloured blob and reports its centre and size", () => {
    const tracker = new HandTracker();
    const frame = blankFrame();
    paint(frame, 40, 50, 24, 28);
    const result = tracker.process(frame, WIDTH, HEIGHT, 0);

    expect(result.present).toBe(true);
    expect(result.x).toBeGreaterThan(0.3);
    expect(result.x).toBeLessThan(0.5);
    expect(result.y).toBeGreaterThan(0.55);
    expect(result.size).toBeGreaterThan(0.2);
    expect(result.area).toBeGreaterThan(20);
    expect(result.confidence).toBeGreaterThan(0.3);
  });

  it("follows a moving blob instead of a static face-shaped blob", () => {
    const tracker = new HandTracker();
    const first = blankFrame();
    paint(first, 20, 6, 26, 30); // static "face" near the top
    paint(first, 70, 52, 22, 26); // hand, lower in frame
    const initial = tracker.process(first, WIDTH, HEIGHT, 0);
    expect(initial.present).toBe(true);
    expect(initial.y).toBeGreaterThan(0.5);

    const second = blankFrame();
    paint(second, 20, 6, 26, 30);
    paint(second, 34, 50, 22, 32); // hand swept left
    const moved = tracker.process(second, WIDTH, HEIGHT, 33);
    expect(moved.present).toBe(true);
    expect(moved.x).toBeLessThan(0.4);
    expect(moved.y).toBeGreaterThan(0.5);
    expect(moved.motion).toBeGreaterThan(0);
  });

  it("rejects an enormous skin-coloured background", () => {
    const tracker = new HandTracker();
    const frame = blankFrame();
    paint(frame, 0, 0, WIDTH, HEIGHT);
    const result = tracker.process(frame, WIDTH, HEIGHT, 0);
    expect(result.present).toBe(false);
  });
});

describe("HandSmoother", () => {
  it("waits for two detections before claiming presence", () => {
    const smoother = new HandSmoother();
    expect(smoother.update(hand(), 0).present).toBe(false);
    expect(smoother.update(hand(), 33).present).toBe(true);
  });

  it("holds presence through a short dropout, then releases", () => {
    const smoother = new HandSmoother();
    smoother.update(hand(), 0);
    smoother.update(hand(), 33);
    for (let index = 0; index < 6; index += 1) {
      smoother.update(missingHand(), 66 + index * 33);
    }
    expect(smoother.update(hand(), 320).present).toBe(true);

    for (let index = 0; index < 12; index += 1) {
      smoother.update(missingHand(), 353 + index * 33);
    }
    expect(smoother.update(missingHand(), 800).present).toBe(false);
  });

  it("mirrors the camera x axis and maps size/fill to depth and spread", () => {
    const smoother = new HandSmoother();
    smoother.update(hand({ x: 0.2, size: 0.4, fill: 0.3 }), 0);
    const result = smoother.update(hand({ x: 0.2, size: 0.4, fill: 0.3 }), 33);
    expect(result.x).toBeGreaterThan(0.3);
    expect(result.depth).toBeGreaterThan(0.5);
    expect(result.spread).toBeGreaterThan(0.8);
    expect(result.grab).toBeLessThan(0.2);
  });

  it("maps a dense blob to a closed hand", () => {
    const smoother = new HandSmoother();
    smoother.update(hand({ fill: 0.9, size: 0.2 }), 0);
    const result = smoother.update(hand({ fill: 0.9, size: 0.2 }), 33);
    expect(result.grab).toBeGreaterThan(0.8);
    expect(result.spread).toBeLessThan(0.2);
  });
});
