"""Voice and model pickers for the text-to-speech providers.

Split out of ``dodaios/brain/model_catalog.py``, which re-exports
``TTS_CATALOG`` and builds ``PROVIDER_CATALOG`` from it. Plain data: this module
imports nothing heavier than the curated model types.
"""

from __future__ import annotations

from dodaios.brain.curated_models import ModelInfo, _curated
from dodaios.core.kokoro_speakers import KOKORO_SPEAKERS


def _ids(ids: list[str]) -> list[ModelInfo]:
    return [ModelInfo(id=i, label=i) for i in ids]


# TTS catalogs — for most TTS providers the user-facing pick is the VOICE
# (Gemini Charon/Kore, Grok leo/rex, OpenAI alloy/nova, Google Neural2 names);
# Cartesia's meaningful pick is its MODEL (sonic-3.5). The ``[tts]`` config is a
# single block (voice_de/voice_en/model), so the picker only renders on the
# ACTIVE TTS card and sets the global value.
TTS_CATALOG: dict[str, tuple[str, list[ModelInfo]]] = {
    # Piper (on-device). A Piper voice speaks ONE language, so this picker is a
    # speaker choice, not a language choice: the provider still resolves the
    # file from the turn's output language. Both sets are listed; the masculine
    # set is what the install downloads, and the feminine one is fetched on
    # demand (Piper has no feminine European Portuguese voice, so Tugão serves
    # both profiles for pt). Kept in sync with SHERPA_BUNDLES in dodaios/speech/local_models.py.
    "piper-local": (
        "voice",
        _curated(
            [
                ("vits-piper-de_DE-thorsten-medium", "Thorsten — German, masculine"),
                ("vits-piper-en_US-ryan-medium", "Ryan — English, masculine"),
                ("vits-piper-es_ES-davefx-medium", "Dave — Spanish, masculine"),
                ("vits-piper-pt_PT-tugao-medium", "Tugão — European Portuguese, masculine"),
                ("vits-piper-de_DE-ramona-low", "Ramona — German, feminine"),
                ("vits-piper-en_US-amy-medium", "Amy — English, feminine"),
                ("vits-piper-es_ES-sharvard-medium", "Sharvard — Spanish, feminine"),
            ]
        ),
    ),
    # Kokoro (on-device): one bundle holds every speaker, so this is a speaker
    # pick, read from the one speaker table (dodaios/core/kokoro_speakers.py).
    "kokoro-local": (
        "voice",
        _curated([(name, s.label) for name, s in KOKORO_SPEAKERS.items()]),
    ),
    # ElevenLabs picks a VOICE ID (opaque hashes), so the curated list carries
    # human names as labels while the value stays the id. The picker's
    # "use custom" row lets a user paste their OWN voice id (e.g. a cloned
    # voice) instead of a curated one — kept in sync with DEFAULT_VOICES in
    # dodaios/plugins/tts/elevenlabs_tts.py.
    # Inworld — the new premium default (arena-#1 realtime, mid-2026). Voices are
    # multilingual; these native de/en/es/pt voices are the curated pick,
    # kept in sync with DEFAULT_VOICE_* in dodaios/plugins/tts/inworld_tts.py.
    "inworld": (
        "voice",
        _curated(
            [
                ("Josef", "Josef — German, calm assistant (default)"),
                ("Johanna", "Johanna — German, warm"),
                ("Dennis", "Dennis — English, deep narrator"),
                ("Ashley", "Ashley — English, bright"),
                ("Diego", "Diego — Spanish, formal"),
                ("Lupita", "Lupita — Spanish, warm"),
                ("Leonor", "Leonor — European Portuguese"),
                ("Heitor", "Heitor — Brazilian Portuguese, masculine"),
            ]
        ),
    ),
    "elevenlabs": (
        "voice",
        _curated(
            [
                ("onwK4e9ZLuTAKqWW03F9", "Daniel — British, authoritative (default)"),
                ("JBFqnCBsd6RMkjVDRZzb", "George — British, deep narrator"),
                ("IKne3meq5aSn9XLyUdCD", "Charlie — British, mature and warm"),
                ("nPczCjzI2devNBz1zQrb", "Brian — American, deep narrator"),
                ("pNInz6obpgDQGcFmaJgB", "Adam — American, classic AI voice"),
            ]
        ),
    ),
    "gemini-flash-tts": (
        "voice",
        _ids(
            "Charon Kore Orus Iapetus Rasalgethi Algenib Algieba Fenrir Aoede "
            "Zephyr Puck Leda Callirrhoe Autonoe Enceladus Umbriel Despina "
            "Erinome Laomedeia Achernar Alnilam Schedar Gacrux Pulcherrima "
            "Achird Zubenelgenubi Vindemiatrix Sadachbia Sadaltager Sulafat".split()
        ),
    ),
    "grok-voice": (
        "voice",
        _ids(
            "leo rex sal ara eve carina zagan helix orion luna iris altair zenith "
            "perseus helios lux kepler rigel cosmo celeste ursa sirius lumen "
            "castor naksh atlas".split()
        ),
    ),
    "openai-tts": (
        "voice",
        _ids(
            [
                "alloy",
                "ash",
                "ballad",
                "coral",
                "echo",
                "fable",
                "onyx",
                "nova",
                "sage",
                "shimmer",
                "verse",
                "marin",
                "cedar",
            ]
        ),
    ),
    "google-neural2": (
        "voice",
        _ids(
            [
                "en-US-Neural2-A",
                "en-US-Neural2-C",
                "en-US-Neural2-D",
                "en-US-Neural2-F",
                "de-DE-Neural2-B",
                "de-DE-Neural2-C",
                "de-DE-Neural2-D",
                "de-DE-Neural2-F",
            ]
        ),
    ),
    "cartesia": (
        "model",
        _curated(
            [
                ("sonic-3.5", "Sonic 3.5 (stable)"),
                ("sonic-3", "Sonic 3"),
                ("sonic-3-latest", "Sonic 3 latest (preview track)"),
            ]
        ),
    ),
    # OpenRouter TTS (the last-resort gateway) — the model picker offers ONLY the
    # four allowlisted, production-grade speech models. The five open-source slop
    # models (Kokoro, Orpheus, CSM-1B, both Zonos) are UNLISTED per the hard
    # allowlist (dodaios/plugins/tts/curated_catalog.py) — they fail the premium
    # multilingual bar on de/es coverage, beta stability, or GPU dependence. Every
    # id here must satisfy curated_catalog.is_allowed("openrouter", id) — guarded
    # by tests/unit/plugins/tts/test_openrouter_curation.py.
    "openrouter-tts": (
        "model",
        _ids(
            [
                "google/gemini-3.1-flash-tts-preview",
                "x-ai/grok-voice-tts-1.0",
                "microsoft/mai-voice-2",
                "mistralai/voxtral-mini-tts-2603",
            ]
        ),
    ),
}


__all__ = ["TTS_CATALOG"]
