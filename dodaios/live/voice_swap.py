"""Speak a live call's answers with the app's own voice (``[tts] speak_calls``).

The live model still listens and thinks; only the voice changes. The
provider's audio is dropped, and the answer's words, as the provider
transcribes them, are spoken by the configured read-aloud voice one sentence
at a time and sent as the call's audio at the rate the call plays. A barge-in
drops every sentence not yet spoken.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from dodaios.plugins.tts import build_tts_from_config
from dodaios.realtime.audio import StreamingPcm16Resampler

log = logging.getLogger(__name__)

#: A sentence ends at ., !, ? or … followed by whitespace (or the end of a turn).
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


class VoiceSwap:
    """Turns an answer's transcript into the call's audio, in the app's voice."""

    def __init__(
        self,
        config: Any,
        *,
        output_rate: int,
        send_pcm: Callable[[bytes], Awaitable[None]],
        language: Callable[[], str],
    ) -> None:
        self._tts = build_tts_from_config(config.tts)
        self._output_rate = int(output_rate)
        self._send_pcm = send_pcm
        self._language = language
        self._pending = ""
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task[None] | None = None

    def feed(self, text: str) -> None:
        """Take more of the answer; every finished sentence is queued to speak."""
        self._pending += text
        parts = _SENTENCE_END.split(self._pending)
        self._pending = parts.pop()
        for sentence in parts:
            self._enqueue(sentence)

    def flush(self) -> None:
        """The answer is complete: speak what is left of it."""
        rest, self._pending = self._pending, ""
        self._enqueue(rest)

    def cancel(self) -> None:
        """The person talked over the answer: drop what was not said yet."""
        self._pending = ""
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
        if self._worker is not None:
            self._worker.cancel()
            self._worker = None

    async def idle(self) -> None:
        """Wait until every queued sentence has been spoken (tests, shutdown)."""
        worker = self._worker
        if worker is None:
            return
        await self._queue.join()

    async def close(self) -> None:
        self.cancel()

    def _enqueue(self, sentence: str) -> None:
        sentence = sentence.strip()
        if not sentence:
            return
        self._queue.put_nowait(sentence)
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._speak(), name="live-app-voice")

    async def _speak(self) -> None:
        while True:
            sentence = await self._queue.get()
            try:
                await self._speak_one(sentence)
            except asyncio.CancelledError:
                self._queue.task_done()
                raise
            except Exception:  # noqa: BLE001  # broad-except: one bad sentence must not end the call
                log.warning("live app voice could not speak a sentence", exc_info=True)
            self._queue.task_done()

    async def _speak_one(self, sentence: str) -> None:
        resampler: StreamingPcm16Resampler | None = None
        source_rate = 0
        async for chunk in self._tts.synthesize(sentence, language_code=self._language() or None):
            if not chunk.pcm:
                continue
            if resampler is None or chunk.sample_rate != source_rate:
                source_rate = int(chunk.sample_rate)
                resampler = (
                    StreamingPcm16Resampler(source_rate, self._output_rate)
                    if source_rate != self._output_rate
                    else None
                )
            pcm = resampler.process(chunk.pcm) if resampler is not None else chunk.pcm
            if pcm:
                await self._send_pcm(pcm)


__all__ = ["VoiceSwap", "build_tts_from_config"]
