"""The Sentinel Ring for the floating desktop window.

The desktop twin of the built-in look ``dodaios/ui/looks/builtin/sentinel-ring``:
a golden network of linked nodes, circuit traces and sparks around a glowing
core. It reads the look's own ``params.js``, so sizes, speeds and colours are
defined once for both (the guard test pins that).

The overlay feeds it through the same seam as the voice orb,
``render(t, mode, ext_level) -> PIL.Image``, but the frame is RGBA with a real
alpha channel: the glow must fade into the desktop (ADR-0048). Where the
window cannot show per-pixel alpha, :func:`on_dark_disc` turns the frame into
the colour-keyed fallback.

Drawing: the scene is projected with numpy, stroked with Pillow at twice the
window size and box-filtered down (that is the anti-aliasing), then given a
blurred copy of itself as bloom and mapped through a gold ramp. Only the
assistant's own voice (``ext_level`` while speaking) changes the size; the
microphone never does.
"""

from __future__ import annotations

import colorsys
import json
import math
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

TAU = math.pi * 2.0

#: Surface modes (``dodaios.ui.dodaiosbar.modes.MODES``) mapped onto the look's
#: voice states. Look states themselves pass through unchanged.
MODE_STATE: dict[str, str] = {
    "idle": "idle",
    "listen": "listening",
    "dictate": "listening",
    "think": "thinking",
    "dictate_transcribing": "thinking",
    "speak": "speaking",
    "notice": "paused",
    "connect": "connecting",
}

#: Drawing happens at this multiple of the window size, then is filtered down.
_SUPERSAMPLE = 2
#: A frame slower than this (on average) leaves too little of the 16.7 ms a
#: 60 fps frame has for the window to show it; the renderer then draws at
#: plain resolution instead.
_SLOW_FRAME_S = 0.0135
#: Horizontal stretch and camera distance of the page's projection.
_SX = 1.18
_CAMERA = 3.4
#: How much of the box the shell fills at full size (the page's 0.82).
_FILL = 0.74
#: Light gain before the gold ramp: the window is small, so the network is dense.
_GAIN = 0.42


def _params_text() -> str:
    from dodaios.ui.looks import loader

    return (loader.builtin_root() / "sentinel-ring" / "params.js").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _cached_params() -> str:
    return _params_text()


def load_params() -> dict[str, Any]:
    """The look's shared parameters, parsed from the object in ``params.js``."""
    text = _cached_params()
    return json.loads(text[text.index("{") : text.rindex("}") + 1])


def state_for(params: dict[str, Any], mode: str) -> str:
    state = MODE_STATE.get(mode, mode)
    return state if state in params["states"] else "idle"


def size_target(params: dict[str, Any], state: str, output: float, t: float) -> float:
    """The size the ring heads for, as a fraction of its box (same rule as pose.js)."""
    s = params["size"]
    if state == "speaking":
        return s["speakQuiet"] + (s["speakLoud"] - s["speakQuiet"]) * max(0.0, min(1.0, output))
    if state == "listening":
        return s["idle"] * (
            1 + params["listenSwellDepth"] * math.sin(TAU * params["listenSwellHz"] * t)
        )
    return s["idle"]


def smooth_size(params: dict[str, Any], current: float, target: float, dt: float) -> float:
    """Quick to grow, slow to settle (same rule as pose.js)."""
    tau = params["attackSeconds"] if target > current else params["releaseSeconds"]
    return current + (target - current) * (1 - math.exp(-max(0.0, dt) / tau))


def _norm(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _nearest(points: np.ndarray, count: np.ndarray) -> list[tuple[int, int]]:
    """Undirected links from each point to its ``count[i]`` nearest neighbours."""
    d = ((points[:, None, :] - points[None, :, :]) ** 2).sum(-1)
    np.fill_diagonal(d, np.inf)
    order = np.argsort(d, axis=1)
    seen: set[tuple[int, int]] = set()
    out: list[tuple[int, int]] = []
    for i in range(len(points)):
        for j in order[i, : int(count[i])]:
            key = (min(i, int(j)), max(i, int(j)))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


#: Offsets of a 7 x 7 dot kernel and their squared distance from its centre.
_KERNEL_DY, _KERNEL_DX = (a.ravel() for a in np.mgrid[-3:4, -3:4])
_KERNEL_D2 = (_KERNEL_DX * _KERNEL_DX + _KERNEL_DY * _KERNEL_DY).astype(np.float64)


class _Accumulator:
    """Light added up per pixel: every splat is collected, then summed in one bincount."""

    def __init__(self, n: int) -> None:
        self._n = n
        self._idx: list[np.ndarray] = []
        self._val: list[np.ndarray] = []

    def add(self, iy: np.ndarray, ix: np.ndarray, values: np.ndarray) -> None:
        n = self._n
        inside = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n)
        self._idx.append(iy[inside] * n + ix[inside])
        self._val.append(np.asarray(values, dtype=np.float32)[inside])

    def total(self) -> np.ndarray:
        n = self._n
        if not self._idx:
            return np.zeros((n, n), dtype=np.float32)
        summed = np.bincount(
            np.concatenate(self._idx), weights=np.concatenate(self._val), minlength=n * n
        )
        return summed.astype(np.float32).reshape(n, n)


@dataclass
class _Pulse:
    a: int
    b: int
    speed: float
    hops: int
    p: float = 0.0


@dataclass
class _Live:
    amp: float
    spin: float
    core: float
    pulses: float
    dim: float
    extra: dict[str, float] = field(default_factory=dict)


class SentinelRingRenderer:
    """Renders the Sentinel Ring as an RGBA frame (straight alpha)."""

    def __init__(self, *, size: int = 216, seed: int = 0x5E7714E1) -> None:
        self._p = load_params()
        self._size = int(size)
        self._supersample = _SUPERSAMPLE
        self._ss = self._size * self._supersample
        #: Recent frame cost, to drop to plain resolution on a machine too slow for 60 fps.
        self._frame_cost = 0.0
        self._frames = 0
        rng = np.random.default_rng(seed)
        self._rng = rng

        n = int(self._p["nodes"])
        i = np.arange(n)
        y = 1 - (i / (n - 1)) * 2
        r = np.sqrt(np.maximum(0.0, 1 - y * y))
        th = math.pi * (3 - math.sqrt(5)) * i
        jitter = (rng.random((n, 3)) - 0.5) * 0.07
        self._nodes = _norm(np.stack([np.cos(th) * r, y, np.sin(th) * r], axis=1) + jitter)
        self._node_h = rng.random(n)
        self._node_seed = rng.random(n) * TAU
        self._hub = rng.random(n) < 0.07
        self._edges = np.array(_nearest(self._nodes, np.where(self._hub, 6, 3)), dtype=np.int64)
        a, b = self._nodes[self._edges[:, 0]], self._nodes[self._edges[:, 1]]
        kink = 1 + (rng.random(len(self._edges)) - 0.5) * 0.09
        self._mids = _norm(a + b) * kink[:, None]
        self._mid_h = (self._node_h[self._edges[:, 0]] + self._node_h[self._edges[:, 1]]) / 2
        self._adj: list[list[int]] = [[] for _ in range(n)]
        for ea, eb in self._edges:
            self._adj[int(ea)].append(int(eb))
            self._adj[int(eb)].append(int(ea))

        trace_pts: list[list[float]] = []
        self._trace_slices: list[tuple[int, int, bool]] = []
        trace_h: list[float] = []
        for _ in range(300):
            lon = rng.random() * TAU
            lat = math.asin(rng.random() * 2 - 1) * 0.95
            direction = int(rng.random() < 0.5)
            steps = 3 + int(rng.random() * 9)
            step = (0.025 + rng.random() * 0.05) * (-1 if rng.random() < 0.5 else 1)
            rr = 0.97 + rng.random() * 0.05
            start = len(trace_pts)
            h = rng.random()
            for _s in range(steps + 1):
                trace_pts.append(
                    [
                        rr * math.cos(lat) * math.cos(lon),
                        rr * math.sin(lat),
                        rr * math.cos(lat) * math.sin(lon),
                    ]
                )
                trace_h.append(h)
                if direction:
                    lon += step / max(0.3, math.cos(lat))
                else:
                    lat = max(-1.45, min(1.45, lat + step))
                if rng.random() < 0.28:
                    direction ^= 1
            self._trace_slices.append((start, len(trace_pts), bool(rng.random() < 0.22)))
        self._traces = np.array(trace_pts)
        self._trace_h = np.array(trace_h)
        self._trace_starts = np.array([s for s, _e, _b in self._trace_slices], dtype=np.int64)
        self._trace_lengths = np.array([e - s for s, e, _b in self._trace_slices], dtype=np.float64)
        ta: list[int] = []
        tid: list[int] = []
        for k, (s, e, _b) in enumerate(self._trace_slices):
            ta.extend(range(s, e - 1))
            tid.extend([k] * (e - 1 - s))
        ta_arr = np.array(ta, dtype=np.int64)
        tid_arr = np.array(tid, dtype=np.int64)
        trace_bright = np.array([b for _s, _e, b in self._trace_slices], dtype=bool)
        self._trace_seg = (ta_arr, ta_arr + 1, tid_arr, trace_bright[tid_arr])

        self._spokes = _norm(rng.random((18, 3)) - 0.5)
        self._spoke_h = rng.random(18)
        self._spoke_bright = rng.random(18) < 0.4

        centers = _norm(rng.random((9, 3)) - 0.5) * (0.25 + rng.random((9, 1)) * 0.45)
        self._inner = centers[np.arange(200) % 9] + (rng.random((200, 3)) - 0.5) * 0.48
        self._inner_h = rng.random(200)
        self._inner_edges = np.array(_nearest(self._inner, np.full(200, 3)), dtype=np.int64)
        self._inner_links = np.stack(
            [(rng.random(50) * 200).astype(np.int64), (rng.random(50) * n).astype(np.int64)], axis=1
        )

        dv = _norm(rng.random((1400, 3)) - 0.5)
        shell = rng.random(1400) < 0.85
        dr = np.where(shell, 0.88 + rng.random(1400) * 0.16, 0.25 + rng.random(1400) * 0.6)
        self._dust = dv * dr[:, None]
        self._dust_seed = rng.random(1400) * TAU
        self._dust_big = rng.random(1400) < 0.06
        self._dust_h = rng.random(1400)

        seg = np.linspace(0, TAU, 141)
        self._ring_unit = np.stack([np.cos(seg), np.zeros_like(seg), np.sin(seg)], axis=1)

        half = self._size / 2.0
        span = (np.arange(self._size, dtype=np.float32) + 0.5) - half
        yy, xx = np.meshgrid(span, span, indexing="ij")
        self._xx, self._yy = xx, yy
        self._radius_px = np.sqrt(xx * xx + yy * yy)

        idle = self._p["states"]["idle"]
        self._cur = _Live(idle["amp"], idle["spin"], idle["core"], idle["pulses"], idle["dim"])
        self._hue = float(self._p["hue"])
        self._yaw = 0.6
        self._env = 0.3
        self._size_frac = float(self._p["size"]["idle"])
        self._hist = np.full(64, 0.3, dtype=np.float64)
        self._hist_idx = 0
        self._hist_t = 0.0
        self._pulses: list[_Pulse] = []
        self._pulse_acc = 0.0
        self._last_t: float | None = None
        self._state = "idle"
        #: Per point set (keyed by its ``h`` array): when each point hears the voice.
        self._lags: dict[int, np.ndarray] = {}
        #: One persistent ``h`` array per ring, so each ring keeps its own lag entry.
        self._ring_h = [np.full(len(self._ring_unit), 0.5) for _ in range(6)]

    # -- public seam ---------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    def render(self, t: float, mode: str, ext_level: float | None) -> Image.Image:
        p = self._p
        dt = 0.0 if self._last_t is None else min(0.05, max(0.0, t - self._last_t))
        self._last_t = t
        state = state_for(p, mode)
        self._state = state
        target = p["states"][state]
        k = 1 - math.pow(0.02, dt) if dt > 0 else 0.0
        cur = self._cur
        cur.amp += (target["amp"] - cur.amp) * k
        cur.spin += (target["spin"] - cur.spin) * k
        cur.core += (target["core"] - cur.core) * k
        cur.pulses += (target["pulses"] - cur.pulses) * k
        cur.dim += (target["dim"] - cur.dim) * k
        hue_target = p["errorHue"] if state == "error" else p["hue"]
        self._hue += (hue_target - self._hue) * k
        self._yaw += dt * cur.spin

        # Only the assistant's voice moves the ring; the microphone level is ignored.
        output = (
            max(0.0, min(1.0, float(ext_level)))
            if (state == "speaking" and ext_level is not None)
            else 0.0
        )
        self._size_frac = smooth_size(p, self._size_frac, size_target(p, state, output, t), dt)

        raw = (
            0.3 + 0.7 * output
            if state == "speaking"
            else (0.4 + 0.3 * math.sin(t * 2.5) if state == "listening" else 0.3)
        )
        self._env += (raw - self._env) * (1 - math.exp(-dt * 5))
        self._push_env(t, self._env)

        started = time.perf_counter()
        frame = self._colorize(self._draw(t, state))
        self._watch_cost(time.perf_counter() - started)
        return frame

    @property
    def supersample(self) -> int:
        return self._supersample

    def _watch_cost(self, seconds: float) -> None:
        """Drop to plain resolution once frames keep costing more than 60 fps allows."""
        self._frames += 1
        self._frame_cost += (seconds - self._frame_cost) * 0.05
        if self._supersample > 1 and self._frames > 90 and self._frame_cost > _SLOW_FRAME_S:
            self._supersample = 1
            self._ss = self._size
            self._lags.clear()

    # Compatibility no-ops for the shared surface (the voice orb has the same pair).
    def start_mouth_anim(self, duration_s: float, t_now: float) -> None:
        """The ring has no mouth; speaking is carried by the swell."""

    def stop_mouth_anim(self) -> None:
        """Counterpart to :meth:`start_mouth_anim`; nothing to stop."""

    # -- internals -----------------------------------------------------

    def _push_env(self, t: float, e: float) -> None:
        if t - self._hist_t > 0.5:
            self._hist_t = t
        while self._hist_t < t:
            self._hist_t += 0.01
            self._hist_idx += 1
            self._hist[self._hist_idx % 64] = e

    def _project(
        self, v: np.ndarray, h: np.ndarray, cam: tuple[float, float, float, float, float, float]
    ) -> np.ndarray:
        """Points (n,3) → columns x, y, depth (0..1), activity — the page's project()."""
        cy, sy, ct, st, radius, amp = cam
        # How long each point waits to hear the voice depends only on where it sits,
        # so a point set that never changes computes it once.
        key = id(h)
        lag = self._lags.get(key)
        if lag is None or len(lag) != len(v):
            rad = np.linalg.norm(v, axis=1)
            lag = np.rint((0.03 + rad * 0.22 + h * 0.14) * 100).astype(np.int64)
            self._lags[key] = lag
        e = self._hist[(self._hist_idx - lag) % 64] - 0.3
        act = np.maximum(0.0, e) * (0.5 + h) * amp * 4
        breath = 1 + 0.012 * math.sin(self._last_t * 1.5 if self._last_t else 0.0)
        d = breath + amp * (0.55 + 0.9 * h) * e
        x, y, z = v[:, 0] * d, v[:, 1] * d, v[:, 2] * d
        x1 = x * cy - z * sy
        z1 = x * sy + z * cy
        y2 = y * ct - z1 * st
        z2 = y * st + z1 * ct
        f = _CAMERA / (_CAMERA - z2)
        c = self._ss / 2.0
        return np.stack(
            [c + x1 * f * radius * _SX, c + y2 * f * radius, np.clip((z2 + 1) / 2, 0, 1), act],
            axis=1,
        )

    def _draw(self, t: float, state: str) -> np.ndarray:
        cur = self._cur
        ss = self._supersample
        radius = (self._ss / (2 * _SX)) * _FILL * self._size_frac
        amp = 0.24 * cur.amp
        tilt = 0.32 + math.sin(t * 0.21) * 0.06
        cam = (
            math.cos(self._yaw),
            math.sin(self._yaw),
            math.cos(tilt),
            math.sin(tilt),
            radius,
            amp,
        )

        acc = _Accumulator(self._ss)
        # Every straight segment of the frame is collected, then stroked in one pass.
        seg_a: list[np.ndarray] = []
        seg_b: list[np.ndarray] = []
        seg_v: list[np.ndarray] = []
        seg_w: list[np.ndarray] = []

        def segments(pa: np.ndarray, pb: np.ndarray, value: np.ndarray, width: np.ndarray) -> None:
            seg_a.append(pa[:, :2])
            seg_b.append(pb[:, :2])
            seg_v.append(np.broadcast_to(value, (len(pa),)))
            seg_w.append(np.broadcast_to(width, (len(pa),)))

        nodes = self._project(self._nodes, self._node_h, cam)

        inner = self._project(self._inner, self._inner_h, cam)
        for pa, pb in (
            (inner[self._inner_edges[:, 0]], inner[self._inner_edges[:, 1]]),
            (inner[self._inner_links[:, 0]], nodes[self._inner_links[:, 1]]),
        ):
            d = (pa[:, 2] + pb[:, 2]) / 2
            segments(pa, pb, 0.03 + d * d * 0.28, 0.5 + d * 0.5)

        mids = self._project(self._mids, self._mid_h, cam)
        pa, pb = nodes[self._edges[:, 0]], nodes[self._edges[:, 1]]
        d = (pa[:, 2] + pb[:, 2]) / 2
        segments(pa, mids, 0.08 + d * d * 0.5, 0.5 + d * 0.7)
        segments(mids, pb, 0.08 + d * d * 0.5, 0.5 + d * 0.7)

        tp = self._project(self._traces, self._trace_h, cam)
        ta, tb, tid, bright = self._trace_segments()
        depth = np.add.reduceat(tp[:, 2], self._trace_starts) / self._trace_lengths
        d = depth[tid]
        segments(
            tp[ta],
            tp[tb],
            np.where(bright, 0.1 + d * d * 0.8, 0.05 + d * d * 0.4),
            np.where(bright, 1 + d * 1.1, 0.6 + d * 0.6),
        )

        for ring_h, (rr, incl, spin, lw, alpha) in zip(
            self._ring_h,
            (
                (1.04, 0.12, 0.0, 3.2, 0.95),
                (1.0, 0.12, 0.0, 1.0, 0.6),
                (0.78, -0.35, self._yaw * 0.4, 1.6, 0.6),
                (1.0, math.pi / 2, 0.3, 1.1, 0.55),
                (1.0, math.pi / 2, 1.9, 0.9, 0.4),
                (1.14, 0.75, -self._yaw * 1.6, 1.0, 0.35),
            ),
            strict=True,
        ):
            u = self._ring_unit * rr
            ci, si, cs, sn = math.cos(incl), math.sin(incl), math.cos(spin), math.sin(spin)
            y1 = -u[:, 2] * si
            z1 = u[:, 2] * ci
            v = np.stack([u[:, 0] * cs - z1 * sn, y1, u[:, 0] * sn + z1 * cs], axis=1)
            rp = self._project(v, ring_h, cam)
            # Back half dim, front half bright, like the page's depth buckets.
            front = (rp[:-1, 2] + rp[1:, 2]) / 2 >= 0.5
            segments(
                rp[:-1],
                rp[1:],
                np.where(front, alpha * 0.95, alpha * 0.35),
                np.where(front, lw * 1.1, lw * 0.7),
            )

        c = self._ss / 2.0
        spokes = self._project(self._spokes, self._spoke_h, cam)
        centre = np.full_like(spokes, c)
        segments(
            centre,
            spokes,
            np.where(self._spoke_bright, 0.1 + spokes[:, 2] * 0.55, 0.05 + spokes[:, 2] * 0.25),
            np.where(self._spoke_bright, 1.4, 0.7),
        )

        self._step_pulses(state)
        heads: list[tuple[float, float, float, float]] = []
        if self._pulses:
            pa = nodes[[p.a for p in self._pulses]]
            pb = nodes[[p.b for p in self._pulses]]
            frac = np.array([p.p for p in self._pulses])[:, None]
            head = pa + (pb - pa) * frac
            segments(pa, head, 0.2 + head[:, 2] * 0.6, np.full(len(head), 1.5))
            heads = [(float(x), float(y), float(dd), 0.0) for x, y, dd, _ in head]

        self._stroke(
            acc,
            np.concatenate(seg_a),
            np.concatenate(seg_b),
            np.concatenate(seg_v),
            np.concatenate(seg_w),
        )

        # Nodes and pulse heads: small round dots, splatted as 3 x 3 or 5 x 5 kernels.
        tw = 0.55 + 0.45 * np.sin(t * 2.2 + self._node_seed * 3)
        node_r = np.where(self._hub, 2.2, 1.0) * (0.5 + nodes[:, 2]) * (1 + nodes[:, 3] * 1.5) * ss
        node_a = np.minimum(1.0, (0.1 + nodes[:, 2] ** 2 * 0.85) * tw * (1 + nodes[:, 3] * 4))
        self._dots(acc, nodes[:, 0], nodes[:, 1], node_r, node_a)
        if heads:
            hd = np.array(heads)
            self._dots(
                acc,
                hd[:, 0],
                hd[:, 1],
                (1.4 + hd[:, 2] * 1.8) * ss,
                np.minimum(1.0, 0.6 + hd[:, 2] * 0.4),
            )

        # Glitter and the inner cells: single pixels, splatted additively.
        dust = self._project(self._dust, self._dust_h, cam)
        twd = np.maximum(0.0, np.sin(t * (1.5 + self._dust_seed) + self._dust_seed * 7))
        dust_a = np.minimum(1.0, (0.08 + dust[:, 2] * 0.7) * twd * (1 + dust[:, 3] * 3))
        self._splat(acc, dust[:, 0], dust[:, 1], dust_a, big=self._dust_big)
        inner_a = np.minimum(1.0, (0.1 + inner[:, 2] * 0.5) * (1 + inner[:, 3] * 4))
        self._splat(acc, inner[:, 0], inner[:, 1], inner_a, big=np.zeros(len(inner), dtype=bool))

        # Down to the window size: the box filter is the anti-aliasing.
        small = (
            np.minimum(acc.total(), 1.5).reshape(self._size, ss, self._size, ss).mean(axis=(1, 3))
        )

        # The haze and the eye are smooth fields, computed at the window size.
        b = cur.core * (
            0.7 + 0.3 * (self._env if state == "speaking" else 0.5 + 0.5 * math.sin(t * 1.6))
        )
        r_win = radius / ss
        rn = np.sqrt((self._xx / _SX) ** 2 + self._yy**2) / max(1.0, r_win * 1.2)
        small += np.interp(rn, [0.0, 0.5, 1.0], [0.22 * b, 0.07, 0.0]).astype(np.float32)
        er = r_win * (1 + 0.04 * cur.amp * self._env)
        small += np.interp(
            self._radius_px / max(1.0, er * 0.42), [0.0, 0.3, 1.0], [0.55 * b, 0.22 * b, 0.0]
        ).astype(np.float32)
        eye = Image.new("L", (self._size, self._size), 0)
        ed = ImageDraw.Draw(eye)
        cw = self._size / 2.0
        spin_mul = 3 if state == "thinking" else 1
        for rr, a0, a1, lw, al, sp in (
            (0.13, 0, TAU, 1, 0.55, 0),
            (0.18, 0.4, 4.6, 2, 0.75, 0.8),
            (0.24, 0, TAU, 0.8, 0.35, 0),
            (0.3, 1.2, 3.9, 1.4, 0.55, -0.5),
            (0.3, 4.4, 5.9, 1.4, 0.55, -0.5),
            (0.4, 0, TAU, 0.7, 0.22, 0),
        ):
            rot = t * sp * spin_mul
            rad = er * rr
            ed.arc(
                (cw - rad, cw - rad, cw + rad, cw + rad),
                math.degrees(a0 + rot),
                math.degrees(a1 + rot),
                fill=int(min(1.0, al * (0.6 + 0.4 * b)) * 255),
                width=max(1, int(round(lw))),
            )
        rad = er * 0.09
        ed.ellipse(
            (cw - rad, cw - rad, cw + rad, cw + rad), outline=255, width=max(2, int(round(2 + b)))
        )
        small += np.asarray(eye, dtype=np.float32) / 255.0

        # Bloom: two blurred copies added back, like the page's 22 px and 6 px passes.
        base = Image.fromarray(np.clip(small * 255, 0, 255).astype(np.uint8), "L")
        wide = (
            np.asarray(
                base.filter(ImageFilter.GaussianBlur(11 * self._size_frac)), dtype=np.float32
            )
            / 255.0
        )
        near = (
            np.asarray(base.filter(ImageFilter.GaussianBlur(3 * self._size_frac)), dtype=np.float32)
            / 255.0
        )
        out = small + 0.55 * wide + 0.9 * near
        self._pupil = self._radius_px < er * 0.075
        return out

    def _trace_segments(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        return self._trace_seg

    def _stroke(
        self,
        acc: _Accumulator,
        pa: np.ndarray,
        pb: np.ndarray,
        values: np.ndarray,
        widths: np.ndarray,
    ) -> None:
        """Stroke every segment at once: sample along each and add the light up.

        Sampling every pixel leaves no gaps, and each sample weighs its own
        spacing, so a line crossing a pixel adds about its value once. Widths of
        two or more supersampled pixels add the neighbouring row and column.
        Adding (not overwriting) is the page's ``lighter`` compositing.
        """
        n = self._ss
        values = np.clip(values, 0.0, 1.0).astype(np.float32)
        delta = pb - pa
        length = np.hypot(delta[:, 0], delta[:, 1])
        keep = (values >= 0.02) & np.isfinite(length)
        pa, delta, length, values, widths = (
            pa[keep],
            delta[keep],
            length[keep],
            values[keep],
            widths[keep],
        )
        counts = np.minimum(np.ceil(length).astype(np.int64) + 1, 4 * n)
        seg = np.repeat(np.arange(len(pa)), counts)
        starts = np.cumsum(counts) - counts
        inv = 1.0 / np.maximum(1, counts - 1)
        frac = (np.arange(int(counts.sum())) - starts[seg]) * inv[seg]
        x = pa[seg, 0] + delta[seg, 0] * frac
        y = pa[seg, 1] + delta[seg, 1] * frac
        step = np.minimum(1.0, length / np.maximum(1, counts - 1))
        v = (values * step)[seg]
        thick = (widths[seg] * self._supersample) >= 2.0
        ix = x.astype(np.int64)
        iy = y.astype(np.int64)
        for dx, dy, sel in ((0, 0, None), (1, 0, thick), (0, 1, thick), (1, 1, thick)):
            jx, jy, jv = (ix, iy, v) if sel is None else (ix[sel] + dx, iy[sel] + dy, v[sel])
            acc.add(jy, jx, jv)

    def _dots(
        self,
        acc: _Accumulator,
        xs: np.ndarray,
        ys: np.ndarray,
        radii: np.ndarray,
        values: np.ndarray,
    ) -> None:
        """Round dots of up to 3 px radius, as splatted kernels."""
        keep = values > 0.03
        xs, ys, radii, values = xs[keep], ys[keep], radii[keep], values[keep].astype(np.float32)
        ix = np.rint(xs).astype(np.int64)
        iy = np.rint(ys).astype(np.int64)
        # One kernel of offsets; each dot keeps the offsets inside its own radius.
        inside = _KERNEL_D2[None, :] <= (radii * radii)[:, None]
        dot, off = np.nonzero(inside)
        acc.add(iy[dot] + _KERNEL_DY[off], ix[dot] + _KERNEL_DX[off], values[dot])

    def _splat(
        self,
        acc: _Accumulator,
        xs: np.ndarray,
        ys: np.ndarray,
        values: np.ndarray,
        *,
        big: np.ndarray,
    ) -> None:
        keep = values >= 0.03
        for offset in ((0, 0), (1, 0), (0, 1), (1, 1)):
            sel = keep if offset == (0, 0) else keep & big
            acc.add(
                ys[sel].astype(np.int64) + offset[1],
                xs[sel].astype(np.int64) + offset[0],
                values[sel],
            )

    def _step_pulses(self, state: str) -> None:
        dt = 1 / 60
        rng = self._rng
        self._pulse_acc += dt * self._cur.pulses
        while self._pulse_acc > 1:
            self._pulse_acc -= 1
            a, b = self._edges[int(rng.random() * len(self._edges))]
            self._pulses.append(
                _Pulse(int(a), int(b), 1.4 + rng.random() * 2, 5 if state == "thinking" else 3)
            )
        alive: list[_Pulse] = []
        for pulse in self._pulses:
            pulse.p += dt * pulse.speed
            if pulse.p >= 1:
                pulse.hops -= 1
                if pulse.hops <= 0:
                    continue
                nxt = self._adj[pulse.b]
                pulse.a, pulse.b, pulse.p = pulse.b, nxt[int(rng.random() * len(nxt))], 0.0
            alive.append(pulse)
        self._pulses = alive

    def _colorize(self, intensity: np.ndarray) -> Image.Image:
        """Intensity → gold (or red) with a straight alpha channel."""
        level = np.clip(intensity * (_GAIN * 255.0), 0.0, 255.0).astype(np.uint8)
        out = self._lut(round(self._hue % 360, 0), round(self._cur.dim, 2))[level]
        pupil = getattr(self, "_pupil", None)
        if pupil is not None:
            hue = (self._hue % 360) / 360.0
            dark = np.array(colorsys.hls_to_rgb(hue, 0.04, 0.6), dtype=np.float32) * 255.0
            out[pupil, :3] = dark.astype(np.uint8)
            out[pupil, 3] = int(0.9 * self._cur.dim * 255)
        return Image.fromarray(out, "RGBA")

    @staticmethod
    @lru_cache(maxsize=64)
    def _lut(hue_deg: float, dim: float) -> np.ndarray:
        """256 levels of light → RGBA: deep gold at low light, pale gold where it is bright."""
        i = np.arange(256, dtype=np.float32) / 255.0
        hue = hue_deg / 360.0
        low = np.array(colorsys.hls_to_rgb(hue, 0.42, 1.0), dtype=np.float32)
        high = np.array(colorsys.hls_to_rgb(hue, 0.86, 1.0), dtype=np.float32)
        rgb = (low + (high - low) * (i**2.2)[:, None]) * 255.0
        alpha = np.clip(i * 1.8, 0.0, 1.0) * dim * 255.0
        alpha[i < 0.012] = 0.0
        return np.clip(np.column_stack([rgb, alpha]), 0, 255).astype(np.uint8)


def on_dark_disc(
    frame: Image.Image, color_key: tuple[int, int, int] = (255, 0, 255)
) -> Image.Image:
    """The colour-key fallback (ADR-0048): the ring on a dark hard-edged disc.

    Every pixel is either the exact key colour (see-through) or solid, so a
    colour-keyed window shows no pink fringe.
    """
    if frame.mode != "RGBA":
        return frame.convert("RGB")  # already colour-keyed: nothing to composite
    w, h = frame.size
    rgba = np.asarray(frame, dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot(xx + 0.5 - w / 2, yy + 0.5 - h / 2)
    inside = r <= (min(w, h) / 2 - 1)
    disc = np.array([10, 8, 4], dtype=np.float32)
    a = rgba[..., 3:4] / 255.0
    rgb = disc + (rgba[..., :3] - disc) * a
    out = np.where(inside[..., None], rgb, np.array(color_key, dtype=np.float32))
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")
