"""Guards for the on-device Kokoro voice.

What matters here and nowhere else: Kokoro is ONE bundle holding many
speakers, so the speaker is a number handed to every generation. A wrong number
does not fail; it speaks with somebody else's voice. And a non-English turn
must reach the Piper voice of its language instead of an English accent.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pytest

from dodaios.plugins.tts import kokoro_local
from dodaios.plugins.tts.kokoro_local import KOKORO_VOICES, KokoroLocalTTS


class _FakeAudio:
    def __init__(self, seconds: float = 0.3, sample_rate: int = 24_000) -> None:
        self.samples = np.linspace(-0.4, 0.4, int(sample_rate * seconds), dtype=np.float32)
        self.sample_rate = sample_rate


class _FakeEngine:
    """Records each generation's text and speaker id, one callback per sentence."""

    sample_rate = 24_000

    def __init__(self, accent: str) -> None:
        self.accent = accent
        self.calls: list[tuple[str, int, float]] = []

    def generate(self, text: str, *, sid: int, speed: float, callback: Any = None) -> _FakeAudio:
        self.calls.append((text, sid, speed))
        audio = _FakeAudio()
        if callback is not None:
            for sentence in [s for s in text.split(".") if s.strip()]:
                callback(audio.samples, 0.0)
                del sentence
        return audio


@pytest.fixture
def kokoro_installed(monkeypatch: pytest.MonkeyPatch) -> dict[str, _FakeEngine]:
    engines: dict[str, _FakeEngine] = {}
    monkeypatch.setattr(kokoro_local, "bundle_installed", lambda model_id: True)

    def _build(self: KokoroLocalTTS, accent: str) -> _FakeEngine:
        engines[accent] = _FakeEngine(accent)
        return engines[accent]

    monkeypatch.setattr(KokoroLocalTTS, "_build_engine", _build)
    return engines


async def _speak(tts: Any, text: str, language_code: str | None = None, voice: str | None = None):
    chunks = []
    async for chunk in tts.synthesize(text, voice=voice, language_code=language_code):
        chunks.append(chunk)
    return chunks


def test_the_default_speaker_is_george_with_the_british_lexicon(kokoro_installed) -> None:
    tts = KokoroLocalTTS()

    chunks = asyncio.run(_speak(tts, "Good evening, sir. All systems are online.", "en-GB"))

    assert tts.last_voice == "bm_george"
    assert tts.last_voice_provider == "kokoro-local"
    engine = kokoro_installed["gb"]
    # 26 is bm_george in the model's own speaker2id metadata.
    assert engine.calls[0][1] == 26
    assert len(chunks) == 2, "each finished sentence streams as its own chunk"
    assert all(c.sample_rate == 24_000 and c.pcm for c in chunks)


def test_an_american_speaker_loads_the_american_engine(kokoro_installed) -> None:
    tts = KokoroLocalTTS(voice="am_michael")

    asyncio.run(_speak(tts, "Hello there.", "en-US"))

    assert set(kokoro_installed) == {"us"}
    assert kokoro_installed["us"].calls[0][1] == KOKORO_VOICES["am_michael"].speaker_id


def test_a_foreign_voice_name_falls_back_to_the_default() -> None:
    assert kokoro_local.resolve_voice("Charon") == "bm_george"
    assert kokoro_local.resolve_voice(None) == "bm_george"
    assert kokoro_local.resolve_voice("bf_emma") == "bf_emma"


def test_markdown_is_not_read_aloud(kokoro_installed) -> None:
    tts = KokoroLocalTTS()

    asyncio.run(_speak(tts, "**Status:** all `green`.", "en"))

    spoken = kokoro_installed["gb"].calls[0][0]
    assert "*" not in spoken and "`" not in spoken


def test_a_non_english_turn_uses_the_piper_voice_of_its_language(
    kokoro_installed, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dodaios.plugins.tts.piper_local import PiperLocalTTS

    spoken: list[tuple[str, str | None]] = []

    def _voices(self: PiperLocalTTS, language: str | None = None) -> list[str]:
        return ["vits-piper-de_DE-thorsten-medium"] if language == "de" else []

    async def _synth(self: PiperLocalTTS, text: str, voice=None, language_code=None):
        spoken.append((text, language_code))
        self.last_voice = "vits-piper-de_DE-thorsten-medium"
        self.last_voice_provider = "piper-local"
        yield _chunk()

    def _chunk():
        from dodaios.core.protocols import AudioChunk

        return AudioChunk(pcm=b"\x00\x00", sample_rate=22_050, timestamp_ns=0, channels=1)

    monkeypatch.setattr(PiperLocalTTS, "list_voices", _voices)
    monkeypatch.setattr(PiperLocalTTS, "synthesize", _synth)
    tts = KokoroLocalTTS()

    asyncio.run(_speak(tts, "Guten Abend.", "de-DE"))

    assert spoken == [("Guten Abend.", "de-DE")]
    assert tts.last_voice_provider == "piper-local"
    assert not kokoro_installed, "Kokoro must not load for a German turn"


def test_a_non_english_turn_without_a_piper_voice_still_speaks(
    kokoro_installed, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dodaios.plugins.tts.piper_local import PiperLocalTTS

    monkeypatch.setattr(PiperLocalTTS, "list_voices", lambda self, language=None: [])
    tts = KokoroLocalTTS()

    chunks = asyncio.run(_speak(tts, "Bonjour.", "fr-FR"))

    assert chunks, "better an English accent than silence"
    assert tts.last_voice == "bm_george"


def test_no_download_raises_an_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kokoro_local, "bundle_installed", lambda model_id: False)
    tts = KokoroLocalTTS()

    with pytest.raises(RuntimeError, match="API-Keys view"):
        asyncio.run(_speak(tts, "Hello.", "en"))


def test_the_factory_builds_kokoro_with_the_configured_speaker() -> None:
    from dodaios.core.config import TTSConfig
    from dodaios.plugins.tts import build_tts_from_config

    tts = build_tts_from_config(
        TTSConfig(provider="kokoro-local", voice_en="bf_emma", voice_de="Charon")
    )
    assert isinstance(tts, KokoroLocalTTS)
    assert tts._voice == "bf_emma"

    fallback = build_tts_from_config(TTSConfig(provider="kokoro-local", voice_de="Charon"))
    assert fallback._voice == "bm_george"


# -- one fact, several files ---------------------------------------------------


def test_the_bundle_id_matches_the_speech_catalog() -> None:
    from dodaios.speech.local_models import KOKORO_MODEL_ID, SHERPA_BUNDLES, get_local_provider

    assert kokoro_local.KOKORO_BUNDLE == KOKORO_MODEL_ID
    bundle = SHERPA_BUNDLES[KOKORO_MODEL_ID]
    for lexicon, _espeak in kokoro_local._ACCENTS.values():
        assert lexicon in bundle.required_files
    # Not a Piper voice: the Piper provider must never pick this bundle.
    assert bundle.language == "" and bundle.gender == ""
    provider = get_local_provider("kokoro-local")
    assert provider is not None and provider.bundles == (KOKORO_MODEL_ID,)


def test_the_voice_picker_offers_exactly_the_known_speakers() -> None:
    from dodaios.brain.model_catalog import TTS_CATALOG

    _field, models = TTS_CATALOG["kokoro-local"]
    assert [m.id for m in models] == list(KOKORO_VOICES)


def test_the_config_writer_keeps_every_known_speaker() -> None:
    from dodaios.core import config_writer

    assert config_writer._VOICES_FOR_PROVIDER["kokoro-local"] == frozenset(KOKORO_VOICES)
    defaults = config_writer._TTS_DEFAULTS["kokoro-local"]
    assert defaults["voice_en"] == kokoro_local.DEFAULT_VOICE
