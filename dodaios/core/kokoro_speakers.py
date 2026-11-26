"""The English speakers of the local Kokoro-82M v1.0 voice.

Plain data, kept in ``core`` so the three places that need it read ONE table:
the Kokoro TTS plugin (speaker number per generation), the voice picker
(``dodaios/brain/tts_catalog.py``) and the config writer's voice allowlist
(``dodaios/core/tts_voice_defaults.py``). The numbers are the model's own
``speaker2id`` metadata in ``model.onnx``; a wrong number does not fail, it
speaks with somebody else's voice.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KokoroSpeaker:
    """One speaker in the Kokoro v1.0 style table (``voices.bin``)."""

    speaker_id: int
    label: str
    gender: str
    #: "gb" or "us": which lexicon and eSpeak voice the speaker reads with.
    accent: str


#: Used when the config names no Kokoro speaker, or one this model lacks.
KOKORO_DEFAULT_SPEAKER = "bm_george"

KOKORO_SPEAKERS: dict[str, KokoroSpeaker] = {
    "bm_george": KokoroSpeaker(26, "George — British English, masculine", "masculine", "gb"),
    "bm_fable": KokoroSpeaker(25, "Fable — British English, masculine", "masculine", "gb"),
    "bm_lewis": KokoroSpeaker(27, "Lewis — British English, masculine", "masculine", "gb"),
    "bm_daniel": KokoroSpeaker(24, "Daniel — British English, masculine", "masculine", "gb"),
    "bf_emma": KokoroSpeaker(21, "Emma — British English, feminine", "feminine", "gb"),
    "bf_isabella": KokoroSpeaker(22, "Isabella — British English, feminine", "feminine", "gb"),
    "bf_alice": KokoroSpeaker(20, "Alice — British English, feminine", "feminine", "gb"),
    "bf_lily": KokoroSpeaker(23, "Lily — British English, feminine", "feminine", "gb"),
    "am_michael": KokoroSpeaker(16, "Michael — American English, masculine", "masculine", "us"),
    "am_adam": KokoroSpeaker(11, "Adam — American English, masculine", "masculine", "us"),
    "am_onyx": KokoroSpeaker(17, "Onyx — American English, masculine", "masculine", "us"),
    "am_eric": KokoroSpeaker(13, "Eric — American English, masculine", "masculine", "us"),
    "af_heart": KokoroSpeaker(3, "Heart — American English, feminine", "feminine", "us"),
    "af_bella": KokoroSpeaker(2, "Bella — American English, feminine", "feminine", "us"),
    "af_nicole": KokoroSpeaker(6, "Nicole — American English, feminine", "feminine", "us"),
    "af_sarah": KokoroSpeaker(9, "Sarah — American English, feminine", "feminine", "us"),
}

__all__ = ["KOKORO_DEFAULT_SPEAKER", "KOKORO_SPEAKERS", "KokoroSpeaker"]
