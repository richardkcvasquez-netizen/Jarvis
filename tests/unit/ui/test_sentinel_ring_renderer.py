"""The desktop Sentinel Ring renders a see-through frame that follows the voice.

Pixel-exactness against the in-app canvas is not testable (different
rasterizers), so these pin what a person sees: how much of the window the
ring covers in each state, that only the assistant's voice moves it, its
colour, and that the desktop and the in-app look share one parameter file.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from dodaios.ui.looks import loader
from ui.orb.sentinel_ring import SentinelRingRenderer, load_params

SIZE = 216


def _settle(mode: str, level: float | None, seconds: float = 2.0) -> np.ndarray:
    renderer = SentinelRingRenderer(size=SIZE)
    frame = None
    t = 0.0
    while t < seconds:
        frame = renderer.render(t, mode, level)
        t += 1 / 60
    assert frame is not None
    return np.asarray(frame)


def _reach(frame: np.ndarray) -> float:
    """How far from the centre the visible ring reaches, as a fraction of the half-window."""
    alpha = frame[..., 3]
    ys, xs = np.nonzero(alpha > 40)
    half = SIZE / 2
    radius = np.hypot(xs + 0.5 - half, ys + 0.5 - half)
    return float(np.percentile(radius, 99) / half)


def test_frame_is_a_see_through_image_of_the_window_size() -> None:
    frame = _settle("idle", None, seconds=0.2)
    assert frame.shape == (SIZE, SIZE, 4)
    # The corners are empty desktop, the centre is the glowing core.
    assert frame[0, 0, 3] == 0 and frame[-1, -1, 3] == 0
    assert frame[SIZE // 2, SIZE // 2, 3] > 0


def test_speaking_swells_past_idle_and_loud_speech_fills_the_window() -> None:
    idle = _reach(_settle("idle", None))
    quiet = _reach(_settle("speak", 0.05))
    loud = _reach(_settle("speak", 1.0))
    assert idle < quiet < loud
    assert 0.45 < idle < 0.75
    assert loud > 0.85


def test_listening_ignores_the_microphone_level() -> None:
    silent = _reach(_settle("listen", 0.0))
    shouting = _reach(_settle("listen", 1.0))
    assert abs(silent - shouting) < 0.02


def test_the_ring_is_gold_and_turns_red_on_error() -> None:
    def mean_rgb(frame: np.ndarray) -> np.ndarray:
        visible = frame[..., 3] > 120
        return frame[visible][:, :3].astype(float).mean(axis=0)

    r, g, b = mean_rgb(_settle("idle", None))
    assert r > g > b  # warm gold
    er, eg, eb = mean_rgb(_settle("error", None))
    assert er > 1.4 * eg  # red, not gold


def test_paused_is_dimmer_than_idle() -> None:
    idle = _settle("idle", None)[..., 3].astype(float).sum()
    paused = _settle("paused", None)[..., 3].astype(float).sum()
    assert paused < 0.75 * idle


@pytest.mark.parametrize(
    "mode",
    ["idle", "listen", "think", "speak", "dictate", "dictate_transcribing", "notice", "connect"],
)
def test_every_desktop_mode_draws(mode: str) -> None:
    frame = _settle(mode, 0.5, seconds=0.3)
    assert frame[..., 3].max() > 0


def test_desktop_and_in_app_look_share_one_parameter_file() -> None:
    folder = loader.builtin_root() / "sentinel-ring"
    html = (folder / "index.html").read_text(encoding="utf-8")
    assert 'src="params.js"' in html
    text = (folder / "params.js").read_text(encoding="utf-8")
    on_disk = json.loads(text[text.index("{") : text.rindex("}") + 1])
    assert load_params() == on_disk


def test_dark_disc_fallback_has_a_hard_edge_with_no_pink_fringe() -> None:
    from ui.orb.sentinel_ring import on_dark_disc

    frame = on_dark_disc(SentinelRingRenderer(size=SIZE).render(0.0, "speak", 1.0))
    rgb = np.asarray(frame).reshape(-1, 3)
    key = (rgb == (255, 0, 255)).all(axis=1)
    assert key.any() and not key.all()
    # A pixel that is not exactly the key must not be a blend toward it.
    others = rgb[~key].astype(int)
    pinkish = (others[:, 0] > 200) & (others[:, 2] > 200) & (others[:, 1] < 80)
    assert not pinkish.any()
