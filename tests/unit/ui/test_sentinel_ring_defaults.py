"""The Sentinel Ring is the default presence, in the app and on the desktop."""

from __future__ import annotations

from dodaios.core.config import UIConfig
from dodaios.ui.desktop_app import boot_overlay_style
from dodaios.ui.overlay_styles import DEFAULT_OVERLAY_STYLE

class _Owner:
    owns_ambient_duties = True


def test_a_fresh_install_wears_the_sentinel_ring_in_the_app() -> None:
    assert UIConfig().look_id == "sentinel-ring"


def test_an_explicit_look_choice_is_kept() -> None:
    assert UIConfig(look_id="orb").look_id == "orb"
    assert UIConfig(look_id="pulse-ring").look_id == "pulse-ring"


def test_a_fresh_install_shows_the_ring_on_the_desktop_instead_of_the_bar() -> None:
    assert DEFAULT_OVERLAY_STYLE == "voice_orb"
    # The config default is a literal (core does not import the UI); this pins the two together.
    assert UIConfig().orb_style == DEFAULT_OVERLAY_STYLE
    assert boot_overlay_style(None, instance=_Owner()) == "voice_orb"
    assert boot_overlay_style("not-a-style", instance=_Owner()) == "voice_orb"


def test_an_explicit_bar_choice_is_kept() -> None:
    assert UIConfig(orb_style="jarvis_bar").orb_style == "jarvis_bar"
    assert boot_overlay_style("jarvis_bar", instance=_Owner()) == "jarvis_bar"

