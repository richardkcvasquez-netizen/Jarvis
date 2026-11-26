"""Per-provider ``[tts]`` defaults and voice allowlists for the TTS switch.

Split out of ``dodaios/core/config_writer.py``, which imports both tables and
is still the only writer of the config (``set_tts_provider``). Plain data.
"""

from __future__ import annotations

from dodaios.core.kokoro_speakers import KOKORO_DEFAULT_SPEAKER, KOKORO_SPEAKERS

# Provider defaults for the TTS switch. Written to the TOML, but only when
# the respective value does not already match the new provider.
#
# Every provider declared with tier="tts" in dodaios/ui/web/provider_spec.py
# MUST have an entry here, enforced by tests/unit/test_tts_defaults_parity.py.
# Without an entry, set_tts_provider() would pass an empty defaults dict and
# leave a stale model/voice from the previous provider in jarvis.toml.
_TTS_DEFAULTS: dict[str, dict[str, str]] = {
    "inworld": {
        # Inworld reads its per-language voices from the [tts.inworld] subtable
        # (voice_de/voice_en/voice_es/voice_pt), NOT [tts].voice_de — same pattern as
        # Cartesia. The scalar voice_de/voice_en are placeholders never consumed
        # by the Inworld factory path. [tts].model is ignored too (the model
        # comes from [tts.inworld].model or the plugin default inworld-tts-2), so
        # model="" is skipped by _patch_tts_block's falsy gate. language_code=
        # "auto" lets Inworld auto-detect the spoken language per turn.
        "model": "",
        "voice_de": "Charon",  # placeholder; Inworld reads [tts.inworld].voice_de
        "voice_en": "Charon",  # placeholder; Inworld reads [tts.inworld].voice_en
        "language_code": "auto",
    },
    "gemini-flash-tts": {
        # model from dodaios/plugins/tts/gemini_flash_tts.py (factory line:
        #   tts_cfg.model or "gemini-3.1-flash-tts-preview")
        "model": "gemini-3.1-flash-tts-preview",
        "voice_de": "Charon",
        "voice_en": "Charon",
        "language_code": "de-DE",
    },
    "vertex-tts": {
        "model": "gemini-3.1-flash-tts-preview",
        "voice_de": "Charon",
        "voice_en": "Charon",
        "language_code": "de-DE",
    },
    "grok-voice": {
        # model is ignored by the Grok plugin (no model param in GrokVoiceTTS).
        # voice from dodaios/plugins/tts/grok_voice_tts.py: GROK_VOICE_LEO = "leo"
        "model": "",  # Grok ignores model — leave blank
        "voice_de": "leo",
        "voice_en": "leo",
        "language_code": "auto",
    },
    "elevenlabs": {
        # model + voice from dodaios/plugins/tts/elevenlabs_tts.py:
        #   model = tts_cfg.model or "eleven_flash_v2_5"
        #   default_voice = tts_cfg.voice_de or ELEVENLABS_VOICE_DANIEL
        #   ELEVENLABS_VOICE_DANIEL = "onwK4e9ZLuTAKqWW03F9"
        "model": "eleven_flash_v2_5",
        "voice_de": "onwK4e9ZLuTAKqWW03F9",  # Daniel
        "voice_en": "onwK4e9ZLuTAKqWW03F9",
        "language_code": "de-DE",
    },
    "cartesia": {
        # Cartesia reads voice UUIDs from [tts.cartesia].voice_id* (a subtable),
        # NOT from [tts].voice_de/voice_en (dodaios/plugins/tts/__init__.py lines
        # 103-116: ct = tts_cfg.model_extra["cartesia"]). The scalar [tts].voice_de
        # and voice_en keys are never consumed by the Cartesia factory path; setting
        # them to "Charon" keeps them consistent with config-soll.json's tts block  # i18n-allow
        # (which holds "Charon" as a carry-over from the Gemini era) so the
        # drift-guard sees zero drift.
        # model="" because [tts].model is not read by CartesiaTTS at all
        # (DEFAULT_MODEL_ID comes from [tts.cartesia].model_id, not [tts].model).
        # The empty-string gate in _patch_tts_block skips writing it, leaving any
        # prior value untouched — harmless since Cartesia ignores [tts].model.
        "model": "",  # Cartesia ignores [tts].model — leave blank
        "voice_de": "Charon",  # placeholder; Cartesia reads [tts.cartesia].voice_id_de
        "voice_en": "Charon",  # placeholder; Cartesia reads [tts.cartesia].voice_id_en
        "language_code": "auto",
    },
    "google-neural2": {
        # google-neural2 plugin does not yet exist (no dodaios/plugins/tts/
        # google_neural2_tts.py). The factory falls back to gemini-flash-tts.
        # These are minimal safe defaults: empty model/voice strings are
        # skipped by _patch_tts_block's falsy gate, so no values are written
        # until a real plugin provides meaningful defaults. language_code="auto"
        # avoids pinning a stale "de-DE" from a prior provider.
        "model": "",
        "voice_de": "",
        "voice_en": "",
        "language_code": "auto",
    },
    "openai-tts": {
        # openai-tts plugin does not yet exist (no dodaios/plugins/tts/
        # openai_tts.py). The factory falls back to gemini-flash-tts.
        # Same strategy as google-neural2: empty strings are skipped by the
        # falsy gate in _patch_tts_block. When a real plugin is added, update
        # these to the correct model (e.g. "tts-1-hd") and voice (e.g.
        # "onyx" for a masculine default — see OpenAI voice options).
        "model": "",
        "voice_de": "",
        "voice_en": "",
        "language_code": "auto",
    },
    "openrouter-tts": {
        # OpenRouter TTS reuses the shared OpenRouter key and resolves its own
        # model + voice defaults internally (dodaios/plugins/tts/openrouter_tts.py:
        # MODEL_DEFAULT_VOICE / GENERIC_DEFAULT_VOICE). Leave these blank — the
        # falsy gate in _patch_tts_block skips empty values, so the provider picks
        # sensible per-model defaults. This entry exists so the provider-parity
        # test passes and set_tts_provider() can reconcile the [tts] block on a
        # switch to OpenRouter TTS.
        "model": "",
        "voice_de": "",
        "voice_en": "",
        "language_code": "auto",
    },
    "piper-local": {
        # ``language_code`` is the load-bearing key here, not the voices. A Piper
        # voice is MONOLINGUAL: the plugin is handed the turn's resolved language
        # and picks the matching installed voice per turn. Inheriting a
        # predecessor's pinned "de-DE" would therefore hard-wire every answer to
        # the German voice, including the ones the resolver decided to speak in
        # English, Spanish or Portuguese — the runtime-language doctrine broken by a leftover
        # config value rather than by any code. "auto" keeps the decision where
        # it belongs.
        #
        # The installer fetches one voice per reply language — German,
        # English, Spanish and Portuguese (PIPER_DEFAULT_VOICES in
        # dodaios/speech/local_models.py); the German and English ones fill the
        # two voice keys below, and the plugin finds the others by language.
        # They are named rather than left blank so switching away from a cloud provider does not
        # leave "Charon" sitting in the block: the resolver tolerates an unknown
        # name, but the settings screen would keep showing a voice this provider
        # cannot speak with. There is no [tts].model concept for Piper.
        "model": "",
        "voice_de": "vits-piper-de_DE-thorsten-medium",
        "voice_en": "vits-piper-en_US-ryan-medium",
        "language_code": "auto",
    },
    "kokoro-local": {
        # One multi-speaker bundle: both voice keys name the Kokoro speaker, so
        # the settings screen never shows a cloud voice Kokoro cannot speak
        # with. "auto" for the same reason as Piper: a non-English turn is
        # handed to the Piper voice of its language, which needs the per-turn
        # language.
        "model": "",
        "voice_de": KOKORO_DEFAULT_SPEAKER,
        "voice_en": KOKORO_DEFAULT_SPEAKER,
        "language_code": "auto",
    },
}

# Per-provider voice allowlist — when the existing voice does not match the
# new provider, we overwrite with the provider default. Kept in sync with
# `dodaios/plugins/tts/__init__.py`.
_VOICES_FOR_PROVIDER: dict[str, frozenset[str]] = {
    # Every catalogued local Piper voice, not only the two the installer fetches
    # by default. Without this entry a switch to Piper would reset the voice to
    # the default pair every time, silently undoing a user who downloaded Ramona
    # or Amy and chose them — the allowlist is what tells the writer "this value
    # is already valid for this provider, keep it".
    "piper-local": frozenset(
        {
            "vits-piper-de_DE-thorsten-medium",
            "vits-piper-de_DE-ramona-low",
            "vits-piper-en_US-ryan-medium",
            "vits-piper-en_US-amy-medium",
            "vits-piper-es_ES-davefx-medium",
            "vits-piper-es_ES-sharvard-medium",
            "vits-piper-pt_PT-tugao-medium",
        }
    ),
    # Every English Kokoro speaker (dodaios/core/kokoro_speakers.py).
    "kokoro-local": frozenset(KOKORO_SPEAKERS),
    "gemini-flash-tts": frozenset(
        {
            "Charon",
            "Orus",
            "Iapetus",
            "Rasalgethi",
            "Algenib",
            "Algieba",
            "Kore",
            "Fenrir",
            "Aoede",
        }
    ),
    "grok-voice": frozenset({"leo", "rex", "sal", "ara", "eve"}),
    # ElevenLabs uses voice IDs (cryptic hashes) — no whitelist.
}


__all__ = ["_TTS_DEFAULTS", "_VOICES_FOR_PROVIDER"]
