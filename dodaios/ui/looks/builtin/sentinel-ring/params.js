// The Sentinel Ring's shared parameters: ONE definition, read by the in-app
// look (index.html loads this file) and by the desktop renderer
// (ui/orb/sentinel_ring.py parses the object below). Keep the object strict
// JSON: double-quoted keys, no comments, no trailing commas.
window.SENTINEL_RING = {
  "hue": 30,
  "errorHue": 356,
  "nodes": 360,
  "size": { "idle": 0.6, "speakQuiet": 0.75, "speakLoud": 1.0 },
  "attackSeconds": 0.1,
  "releaseSeconds": 0.4,
  "listenSwellHz": 0.4,
  "listenSwellDepth": 0.03,
  "states": {
    "idle":       { "amp": 0.10, "spin": 0.18, "core": 0.60, "pulses": 3,  "dim": 1.0 },
    "connecting": { "amp": 0.12, "spin": 0.45, "core": 0.70, "pulses": 10, "dim": 1.0 },
    "listening":  { "amp": 0.35, "spin": 0.25, "core": 0.80, "pulses": 7,  "dim": 1.0 },
    "thinking":   { "amp": 0.15, "spin": 0.90, "core": 0.85, "pulses": 26, "dim": 1.0 },
    "speaking":   { "amp": 1.00, "spin": 0.30, "core": 1.00, "pulses": 12, "dim": 1.0 },
    "paused":     { "amp": 0.10, "spin": 0.18, "core": 0.60, "pulses": 3,  "dim": 0.45 },
    "error":      { "amp": 0.10, "spin": 0.18, "core": 0.60, "pulses": 0,  "dim": 1.0 }
  }
};
