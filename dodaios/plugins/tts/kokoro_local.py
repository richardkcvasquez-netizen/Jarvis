"""On-device text-to-speech: Kokoro-82M voices played through sherpa-onnx.

The second keyless local voice, next to Piper. Kokoro-82M (Apache-2.0) is a
small StyleTTS2-style model whose English speakers sound markedly more natural
than Piper's, at the price of a larger download (about 350 MB) and more CPU
time per sentence. It runs on the same sherpa-onnx runtime the Piper voices
already use, so it needs no new dependency.

Three facts shape this provider:

**One bundle, many speakers.** A Piper voice is one file per speaker; Kokoro
ships every speaker in one style table (``voices.bin``) and picks one by number
at generation time. The default is ``bm_george``, a British English man.

**English only here.** Kokoro v1.0 also has voices for other languages, but the
sherpa-onnx bundle ships lexicons for English and Chinese only. A turn whose
output language is not English is spoken by the installed Piper voice for that
language when there is one, so the reply is not read in an English accent;
without one, Kokoro reads it and the log says why.

**British and American speakers phonemize differently.** A ``b*_`` speaker
reads with the British lexicon and Received Pronunciation for words the lexicon
lacks; an ``a*_`` speaker with the American ones. Each accent is one engine,
loaded lazily and cached.
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import threading
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from dodaios.core.kokoro_speakers import KOKORO_DEFAULT_SPEAKER, KOKORO_SPEAKERS
from dodaios.core.protocols import AudioChunk
from dodaios.plugins.tts.piper_local import (
    PiperLocalTTS,
    bundle_installed,
    load_sherpa_runtime,
    pcm16,
    sherpa_major_version,
    speech_text,
    voice_files,
)

log = logging.getLogger(__name__)

#: Directory name of the bundle under ``data/models/``; matches
#: ``KOKORO_MODEL_ID`` in ``dodaios/speech/local_models.py`` (a test keeps
#: the two equal).
KOKORO_BUNDLE = "kokoro-multi-lang-v1_0"

#: The speaker used when the config names none, or one this model lacks.
DEFAULT_VOICE = KOKORO_DEFAULT_SPEAKER

#: The English speakers, keyed by their upstream names (dodaios/core/kokoro_speakers.py).
KOKORO_VOICES = KOKORO_SPEAKERS

_DEFAULT_SPEED = 1.0

#: Per accent: the lexicon file in the bundle and the eSpeak NG voice that
#: phonemizes words the lexicon does not list. The eSpeak names are the file
#: names under ``espeak-ng-data/lang/gmw``; "en-gb" is not one of them.
_ACCENTS: dict[str, tuple[str, str]] = {
    "gb": ("lexicon-gb-en.txt", "en-GB-x-rp"),
    "us": ("lexicon-us-en.txt", "en-US"),
}


def _default_threads() -> int:
    """Half the logical CPUs, between 2 and 8.

    Measured on an 8-core desktop CPU: 2 threads generate a sentence about
    twice as slowly as it plays, 8 threads close to real time. More threads
    than physical cores only add contention.
    """
    return max(2, min(8, (os.cpu_count() or 4) // 2))


def resolve_voice(requested: str | None) -> str:
    """A Kokoro speaker name: *requested* when known, else the default."""
    name = (requested or "").strip()
    if name in KOKORO_VOICES:
        return name
    if name:
        log.info("Voice %r is not a Kokoro speaker; using %r.", name, DEFAULT_VOICE)
    return DEFAULT_VOICE


class KokoroLocalTTS:
    """Local Kokoro-82M text-to-speech (keyless, on-device)."""

    name = "kokoro-local"
    supports_streaming = True
    last_voice: str | None = None
    last_voice_provider: str | None = None
    runs_on_device = True

    def __init__(
        self,
        *,
        voice: str | None = None,
        speed: float | None = None,
        num_threads: int | None = None,
    ) -> None:
        self._voice = resolve_voice(voice)
        self._speed = float(speed) if speed is not None and speed > 0 else _DEFAULT_SPEED
        self._num_threads = max(1, int(num_threads)) if num_threads else _default_threads()
        #: accent -> loaded engine.
        self._engines: dict[str, Any] = {}
        self._load_lock = asyncio.Lock()
        self._workers: set[asyncio.Task[Any]] = set()
        #: Speaks the turns Kokoro has no lexicon for; built on first need.
        self._piper: PiperLocalTTS | None = None

    # -- voices ---------------------------------------------------------------
    def list_voices(self, language: str | None = None) -> list[str]:
        """The Kokoro speakers, when the bundle is downloaded."""
        if not bundle_installed(KOKORO_BUNDLE):
            return []
        short = (language or "").lower().split("-", 1)[0]
        if short and short != "en":
            return []
        return list(KOKORO_VOICES)

    def _other_language_voice(self, language_code: str | None) -> PiperLocalTTS | None:
        """The Piper provider when this turn's language is not English and a
        Piper voice for it is installed; otherwise None (Kokoro speaks)."""
        language = (language_code or "").strip().lower().split("-", 1)[0]
        if not language or language in ("en", "auto"):
            return None
        if self._piper is None:
            self._piper = PiperLocalTTS(
                gender=KOKORO_VOICES[self._voice].gender,
                speed=self._speed,
            )
        if self._piper.list_voices(language):
            return self._piper
        log.warning(
            "Kokoro has no %r voice and no local Piper voice for it is installed; "
            "Kokoro reads this reply in English. Download the Piper voices from "
            "the API-Keys view for a native accent.",
            language,
        )
        return None

    # -- engine ---------------------------------------------------------------
    def _build_engine(self, accent: str) -> Any:
        sherpa_onnx = load_sherpa_runtime(
            (
                "OfflineTts",
                "OfflineTtsConfig",
                "OfflineTtsModelConfig",
                "OfflineTtsKokoroModelConfig",
            )
        )
        if sherpa_major_version() >= 2:
            # The generation API changed in sherpa-onnx 2 and this provider has
            # only been verified against 1.x (SHERPA_ONNX_PACKAGE pins < 2).
            raise RuntimeError(
                "The Kokoro voice supports sherpa-onnx 1.x; the installed runtime "
                "is 2.x. Reinstall the local speech runtime from the API-Keys view."
            )
        paths = voice_files(KOKORO_BUNDLE)
        lexicon_name, espeak_voice = _ACCENTS[accent]
        needed = ("model.onnx", "voices.bin", "tokens.txt", "espeak-ng-data", lexicon_name)
        missing = [name for name in needed if name not in paths or not paths[name].exists()]
        if missing:
            raise RuntimeError(
                "The Kokoro voice is not fully downloaded (missing: "
                f"{', '.join(missing)}). Download it from the API-Keys view."
            )
        log.info("Loading local Kokoro voice (%s accent, %d threads)", accent, self._num_threads)
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=str(paths["model.onnx"]),
                    voices=str(paths["voices.bin"]),
                    tokens=str(paths["tokens.txt"]),
                    data_dir=str(paths["espeak-ng-data"]),
                    lexicon=str(paths[lexicon_name]),
                    lang=espeak_voice,
                ),
                num_threads=self._num_threads,
                provider="cpu",
            ),
        )
        return sherpa_onnx.OfflineTts(config)

    async def _engine_for(self, accent: str) -> Any:
        engine = self._engines.get(accent)
        if engine is not None:
            return engine
        async with self._load_lock:
            engine = self._engines.get(accent)
            if engine is None:
                engine = await asyncio.to_thread(self._build_engine, accent)
                self._engines[accent] = engine
        return engine

    # -- synthesis ------------------------------------------------------------
    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language_code: str | None = None,
    ) -> AsyncIterator[AudioChunk]:
        """Speak *text*; sentence by sentence, as Kokoro finishes each one."""
        spoken = speech_text(text)
        if not spoken:
            return
        other = self._other_language_voice(language_code)
        if other is not None:
            async for chunk in other.synthesize(spoken, None, language_code):
                yield chunk
            self.last_voice = other.last_voice
            self.last_voice_provider = other.last_voice_provider
            return
        if not bundle_installed(KOKORO_BUNDLE):
            raise RuntimeError(
                "The Kokoro voice is not downloaded yet, so the on-device voice "
                "cannot speak. Download it from the API-Keys view, or switch "
                "voice output to another provider."
            )
        speaker_name = resolve_voice(voice) if voice else self._voice
        speaker = KOKORO_VOICES[speaker_name]
        engine = await self._engine_for(speaker.accent)
        sample_rate = int(getattr(engine, "sample_rate", 0) or 0) or 24_000

        # Generation runs on a worker thread; finished sentences reach this
        # coroutine through a small bounded queue, ``end`` closes it.
        chunks: queue.Queue[bytes | object] = queue.Queue(maxsize=8)
        end = object()
        stopped, emitted = threading.Event(), threading.Event()
        failure: list[Exception] = []

        def _put(value: bytes | object) -> bool:
            while not stopped.is_set():
                with suppress(queue.Full):  # the reader is just behind: retry
                    chunks.put(value, timeout=0.05)
                    return True
            return False

        def _callback(samples: Any, progress: float) -> int:
            data = pcm16(samples)
            if data:
                emitted.set()
                if not _put(data):
                    return 0
            # sherpa-onnx: 1 continues generation, 0 cancels it.
            return 0 if stopped.is_set() else 1

        def _generate() -> None:
            try:
                audio = engine.generate(
                    spoken, sid=speaker.speaker_id, speed=self._speed, callback=_callback
                )
                if not emitted.is_set():
                    data = pcm16(getattr(audio, "samples", ()))
                    if data:
                        emitted.set()
                        _put(data)
            except Exception as exc:  # broad-except: forwarded to the async owner
                log.debug("Kokoro generation failed; forwarded to the caller", exc_info=True)
                failure.append(exc)
            finally:
                _put(end)

        worker = asyncio.create_task(asyncio.to_thread(_generate), name="kokoro-tts")
        self._workers.add(worker)
        worker.add_done_callback(self._workers.discard)
        self.last_voice = speaker_name
        self.last_voice_provider = self.name
        try:
            while True:
                item = await asyncio.to_thread(chunks.get)
                if item is end:
                    break
                assert isinstance(item, bytes)
                yield AudioChunk(pcm=item, sample_rate=sample_rate, timestamp_ns=0, channels=1)
            await worker
            if failure:
                raise failure[0]
            if not emitted.is_set():
                raise RuntimeError(
                    f"The Kokoro voice '{speaker_name}' generated no audio for this text."
                )
        finally:
            stopped.set()
            # Wake a reader still blocked in chunks.get() on an executor thread.
            with suppress(queue.Full):
                chunks.put_nowait(end)
            if not worker.done():
                with suppress(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(worker), timeout=1.0)

    async def _ensure_client(self) -> None:
        """Warm-up: load the default speaker's engine and run one short phrase,
        so the first real reply does not pay the model load (about 3 s)."""
        if not bundle_installed(KOKORO_BUNDLE):
            return
        try:
            engine = await self._engine_for(KOKORO_VOICES[self._voice].accent)
            sid = KOKORO_VOICES[self._voice].speaker_id
            await asyncio.to_thread(engine.generate, "Ready.", sid=sid, speed=self._speed)
        except Exception as exc:  # broad-except: warm-up must never break boot
            log.debug("Kokoro voice warm-up skipped (%s).", exc)

    async def aclose(self) -> None:
        """Drop the loaded engines so a switched-away provider frees its memory."""
        if self._workers:
            await asyncio.gather(*tuple(self._workers), return_exceptions=True)
        self._engines.clear()
        if self._piper is not None:
            await self._piper.aclose()


__all__ = ["DEFAULT_VOICE", "KOKORO_BUNDLE", "KOKORO_VOICES", "KokoroLocalTTS", "resolve_voice"]
