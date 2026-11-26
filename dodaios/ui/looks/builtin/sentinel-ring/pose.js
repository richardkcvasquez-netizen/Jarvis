// How big the Sentinel Ring is, given the voice state and the voice level.
// Pure functions over the shared parameters (params.js); the page and the
// tests both call them. ui/orb/sentinel_ring.py implements the same rules.
(function (root) {
  "use strict";

  function stateKey(params, state) {
    return Object.prototype.hasOwnProperty.call(params.states, state) ? state : "idle";
  }

  function clamp01(x) {
    const n = Number(x);
    return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0;
  }

  // The size the ring heads for, as a fraction of its box. Only the
  // assistant's own voice (output) moves it; the microphone never does.
  function sizeTarget(params, state, output, t, reducedMotion) {
    const s = params.size;
    const key = stateKey(params, state);
    if (key === "speaking") return s.speakQuiet + (s.speakLoud - s.speakQuiet) * clamp01(output);
    if (key === "listening" && !reducedMotion) {
      return s.idle * (1 + params.listenSwellDepth * Math.sin(2 * Math.PI * params.listenSwellHz * t));
    }
    return s.idle;
  }

  // One smoothing step: quick to grow, slow to settle.
  function smoothSize(params, current, target, dt) {
    const tau = target > current ? params.attackSeconds : params.releaseSeconds;
    const k = 1 - Math.exp(-Math.max(0, dt) / tau);
    return current + (target - current) * k;
  }

  const api = { stateKey, sizeTarget, smoothSize, clamp01 };
  root.SentinelPose = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
