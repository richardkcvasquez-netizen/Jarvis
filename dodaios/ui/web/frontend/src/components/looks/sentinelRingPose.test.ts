/**
 * The Sentinel Ring look's size rules (`dodaios/ui/looks/builtin/sentinel-ring/pose.js`):
 * idle rests at its normal size, speech swells it with the assistant's own
 * voice, listening never follows the microphone, and the swell rises fast
 * and settles slowly. The desktop renderer (`ui/orb/sentinel_ring.py`)
 * implements the same rules against the same `params.js`.
 */
import { beforeAll, describe, expect, it } from "vitest";


interface Params {
  size: { idle: number; speakQuiet: number; speakLoud: number };
  attackSeconds: number;
  releaseSeconds: number;
}
interface Pose {
  stateKey(p: Params, state: string): string;
  sizeTarget(p: Params, state: string, output: number, t: number, reduced: boolean): number;
  smoothSize(p: Params, current: number, target: number, dt: number): number;
}

let P: Params;
let Pose: Pose;

beforeAll(async () => {
  // The look pack's two scripts, imported in the order the page loads them.
  // @ts-expect-error -- a look's scripts are plain browser scripts with no type declarations
  await import("../../../../../looks/builtin/sentinel-ring/params.js");
  // @ts-expect-error -- as above
  await import("../../../../../looks/builtin/sentinel-ring/pose.js");
  const g = window as unknown as { SENTINEL_RING: Params; SentinelPose: Pose };
  P = g.SENTINEL_RING;
  Pose = g.SentinelPose;
});

function settle(state: string, output: number, seconds = 3): number {
  let size = P.size.idle;
  for (let t = 0; t < seconds; t += 1 / 60) {
    size = Pose.smoothSize(P, size, Pose.sizeTarget(P, state, output, t, false), 1 / 60);
  }
  return size;
}

describe("Sentinel Ring size", () => {
  it("rests at the idle size", () => {
    expect(settle("idle", 0)).toBeCloseTo(0.6, 2);
  });

  it("swells past idle when speaking quietly and fills its box when loud", () => {
    const quiet = settle("speaking", 0.05);
    const loud = settle("speaking", 1);
    expect(quiet).toBeGreaterThan(0.6);
    expect(loud).toBeGreaterThan(quiet);
    expect(loud).toBeCloseTo(1, 2);
  });

  it("ignores the microphone while listening", () => {
    expect(Pose.sizeTarget(P, "listening", 1, 0.25, false)).toBe(Pose.sizeTarget(P, "listening", 0, 0.25, false));
  });

  it("rises faster than it settles", () => {
    const up = Pose.smoothSize(P, 0.6, 1, 0.05) - 0.6;
    const down = 1 - Pose.smoothSize(P, 1, 0.6, 0.05);
    expect(up).toBeGreaterThan(down * 2);
  });

  it("holds still while listening when the system asks for reduced motion", () => {
    expect(Pose.sizeTarget(P, "listening", 0, 0.6, true)).toBe(P.size.idle);
  });

  it("treats an unknown state like idle", () => {
    expect(Pose.stateKey(P, "dancing")).toBe("idle");
    expect(Pose.sizeTarget(P, "dancing", 1, 0, false)).toBe(P.size.idle);
  });
});
