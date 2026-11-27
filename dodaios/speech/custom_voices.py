"""Piper voices the person adds by hand, beside the catalogued downloads.

A folder ``<data>/models/custom-piper-<name>/`` holding one Piper voice in the
sherpa-onnx layout (``<voice>.onnx`` carrying sherpa's metadata, ``tokens.txt``
and ``espeak-ng-data``) becomes an on-device voice the Piper provider offers.
The voice's own ``<voice>.onnx.json``, when present, gives its language;
without it the voice is English. Nothing here downloads: the folder is the
person's, and a folder that is incomplete is simply not offered.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from dodaios.speech.local_models import SHERPA_BUNDLES, SherpaBundle, models_root

log = logging.getLogger(__name__)

#: Folder-name prefix that marks a hand-added Piper voice under ``models/``.
CUSTOM_PIPER_PREFIX = "custom-piper-"


def _language(model: Path) -> str:
    """Two-letter language of the voice, from its Piper config; else English."""
    config = model.with_name(model.name + ".json")
    try:
        code = json.loads(config.read_text(encoding="utf-8"))["language"]["code"]
    except FileNotFoundError:
        return "en"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("Custom voice %s: unreadable %s (%s); treating it as English.",
                    model.parent.name, config.name, exc)
        return "en"
    return str(code).replace("-", "_").split("_", 1)[0].lower() or "en"


def _bundle(folder: Path) -> SherpaBundle | None:
    models = sorted(folder.glob("*.onnx"))
    if len(models) != 1:
        log.warning("Custom voice %s needs exactly one .onnx file, found %d; not offered.",
                    folder.name, len(models))
        return None
    return SherpaBundle(
        model_id=folder.name,
        label=folder.name.removeprefix(CUSTOM_PIPER_PREFIX),
        required_files=(models[0].name, "tokens.txt", "espeak-ng-data"),
        language=_language(models[0]),
    )


def custom_piper_bundles(data_dir: str | None = None) -> dict[str, SherpaBundle]:
    """Every hand-added Piper voice folder, keyed by its folder name."""
    root = models_root(data_dir)
    if not root.is_dir():
        return {}
    found: dict[str, SherpaBundle] = {}
    for folder in sorted(root.iterdir()):
        if folder.is_dir() and folder.name.startswith(CUSTOM_PIPER_PREFIX):
            bundle = _bundle(folder)
            if bundle is not None:
                found[folder.name] = bundle
    return found


def sherpa_bundle(model_id: str, *, data_dir: str | None = None) -> SherpaBundle | None:
    """The catalogued bundle for *model_id*, or the hand-added voice of that name."""
    bundle = SHERPA_BUNDLES.get(model_id)
    if bundle is not None or not model_id.startswith(CUSTOM_PIPER_PREFIX):
        return bundle
    return custom_piper_bundles(data_dir).get(model_id)


__all__ = ["CUSTOM_PIPER_PREFIX", "custom_piper_bundles", "sherpa_bundle"]
