"""A Piper voice the person adds by hand becomes a selectable on-device voice.

The person converts a Piper voice to the sherpa-onnx layout and drops it in
``<data>/models/custom-piper-<name>/``. The Piper provider then lists it and
finds its files; a folder that is incomplete or ambiguous is not offered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dodaios.plugins.tts.piper_local import PiperLocalTTS
from dodaios.speech.sherpa_models import model_paths


def _add_voice(models: Path, name: str, *, language: str = "en_GB") -> Path:
    folder = models / f"custom-piper-{name}"
    (folder / "espeak-ng-data").mkdir(parents=True)
    (folder / f"{name}.onnx").write_bytes(b"onnx")
    (folder / f"{name}.onnx.json").write_text(
        json.dumps({"language": {"code": language}}), encoding="utf-8"
    )
    (folder / "tokens.txt").write_text("_ 0\n", encoding="utf-8")
    return folder


@pytest.fixture
def models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("JARVIS__MEMORY__DATA_DIR", str(tmp_path))
    root = tmp_path / "models"
    root.mkdir()
    return root


def test_a_hand_added_voice_is_listed_in_its_language(models: Path) -> None:
    _add_voice(models, "butler", language="en_GB")

    tts = PiperLocalTTS()

    assert "custom-piper-butler" in tts.list_voices()
    assert "custom-piper-butler" in tts.list_voices("en")
    assert "custom-piper-butler" not in tts.list_voices("de")


def test_its_files_are_found_where_it_was_placed(models: Path) -> None:
    folder = _add_voice(models, "butler")

    paths = model_paths("custom-piper-butler")

    assert paths["butler.onnx"] == folder / "butler.onnx"
    assert paths["tokens.txt"] == folder / "tokens.txt"
    assert paths["espeak-ng-data"] == folder / "espeak-ng-data"


def test_an_incomplete_folder_is_not_offered(models: Path) -> None:
    (_add_voice(models, "butler") / "tokens.txt").unlink()

    assert "custom-piper-butler" not in PiperLocalTTS().list_voices()


def test_a_folder_with_two_models_is_not_offered(models: Path) -> None:
    folder = _add_voice(models, "butler")
    (folder / "other.onnx").write_bytes(b"onnx")

    assert "custom-piper-butler" not in PiperLocalTTS().list_voices()
