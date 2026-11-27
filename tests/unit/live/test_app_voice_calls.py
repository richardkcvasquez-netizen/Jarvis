"""A call can speak with the app's own voice instead of the provider's.

With ``[tts] speak_calls`` on, the live model still listens and thinks, but
what the person hears is the configured read-aloud voice: the provider's
audio is dropped, and the answer's words are spoken sentence by sentence and
sent as the call's audio at the rate the call plays. Talking over it drops
what was not said yet.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from dodaios.core.protocols import AudioChunk
from dodaios.live import voice_swap
from dodaios.live.native import NativeLiveVoiceSession
from dodaios.live.state import LiveLedger
from dodaios.live.tools import LiveTools
from dodaios.realtime.protocol import RealtimeEvent
from tests.fakes.fake_native_voice import (
    FakeNativeConnection,
    FakeToolGateway,
    gemini_like_provider,
)

_VOICE_RATE = 12_000  # the app voice's own rate; the call plays at 24 kHz


class _FakeVoice:
    """Speaks each sentence as one chunk of 0.1 s of a level that names it."""

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.release = asyncio.Event()
        self.release.set()

    async def synthesize(
        self, text: str, voice: str | None = None, language_code: str | None = None
    ):
        await self.release.wait()
        self.spoken.append(text)
        samples = _VOICE_RATE // 10
        yield AudioChunk(pcm=b"\x10\x00" * samples, sample_rate=_VOICE_RATE, timestamp_ns=0)


def _config(speak_calls: bool) -> Any:
    return SimpleNamespace(
        brain=SimpleNamespace(reply_language="auto", providers={}, realtime=None),
        voice=SimpleNamespace(realtime_tool_declaration_budget_tokens=0),
        tts=SimpleNamespace(speak_calls=speak_calls, provider="fake"),
    )


def _session(tmp_path, monkeypatch, *, speak_calls: bool):
    fake = _FakeVoice()
    monkeypatch.setattr(voice_swap, "build_tts_from_config", lambda _cfg: fake)
    sent: list[bytes] = []

    async def send_json(_frame):
        return None

    async def send_binary(data):
        sent.append(bytes(data))

    provider = gemini_like_provider()
    session = NativeLiveVoiceSession(
        session_id="app-voice", send_json=send_json, send_binary=send_binary,
        providers=[provider], config=_config(speak_calls),
    )
    ledger = LiveLedger(tmp_path / "ledger.sqlite3")
    session._connection = FakeNativeConnection(creates_responses_automatically=True, model="m")
    session._ledger = ledger
    session._tools = LiveTools(
        FakeToolGateway(), ledger, "app-voice", language="en", backend_model=""
    )
    return session, fake, sent, ledger


async def _drain(session) -> None:
    swap = session._voice_swap
    if swap is not None:
        await swap.idle()


@pytest.mark.asyncio
async def test_the_answer_is_spoken_with_the_app_voice_not_the_provider(tmp_path, monkeypatch):
    session, fake, sent, ledger = _session(tmp_path, monkeypatch, speak_calls=True)
    try:
        provider_pcm = b"\x7f\x7f" * 480
        await session._provider_event(RealtimeEvent(type="audio_delta", audio=AudioChunk(
            pcm=provider_pcm, sample_rate=24_000, timestamp_ns=0)))
        for piece in ("Good evening, sir. ", "All systems ", "are online."):
            await session._provider_event(RealtimeEvent(type="output_transcript_delta", text=piece))
        await session._provider_event(RealtimeEvent(type="turn_complete"))
        await _drain(session)

        assert fake.spoken == ["Good evening, sir.", "All systems are online."]
        assert provider_pcm not in sent
        # Two sentences of 0.1 s each, resampled from 12 kHz to the call's 24 kHz.
        assert sum(len(chunk) for chunk in sent) == pytest.approx(2 * 2400 * 2, rel=0.02)
    finally:
        ledger.close()


@pytest.mark.asyncio
async def test_talking_over_it_drops_what_was_not_said(tmp_path, monkeypatch):
    session, fake, sent, ledger = _session(tmp_path, monkeypatch, speak_calls=True)
    try:
        fake.release.clear()
        for piece in ("First line. ", "Second line. ", "Third line."):
            await session._provider_event(RealtimeEvent(type="output_transcript_delta", text=piece))
        session._speaking = True
        await session._provider_event(RealtimeEvent(type="speech_started"))
        fake.release.set()
        await session._provider_event(RealtimeEvent(type="turn_complete"))
        await _drain(session)

        assert "Second line." not in fake.spoken
        assert "Third line." not in fake.spoken
    finally:
        ledger.close()


@pytest.mark.asyncio
async def test_without_the_switch_the_provider_voice_plays(tmp_path, monkeypatch):
    session, fake, sent, ledger = _session(tmp_path, monkeypatch, speak_calls=False)
    try:
        provider_pcm = b"\x7f\x7f" * 480
        await session._provider_event(RealtimeEvent(type="audio_delta", audio=AudioChunk(
            pcm=provider_pcm, sample_rate=24_000, timestamp_ns=0)))
        hello = RealtimeEvent(type="output_transcript_delta", text="Hello there.")
        await session._provider_event(hello)
        await session._provider_event(RealtimeEvent(type="turn_complete"))

        assert sent == [provider_pcm]
        assert fake.spoken == []
    finally:
        ledger.close()


def test_the_switch_is_saved_and_read_back(tmp_path, monkeypatch):
    from dodaios.core import config_writer
    from dodaios.core.config import load_config

    monkeypatch.setattr(config_writer, "_update_config_soll_section", lambda *_a, **_k: None)
    path = tmp_path / "jarvis.toml"
    path.write_text("[tts]\nprovider = \"piper-local\"\n", encoding="utf-8")
    assert load_config(path).tts.speak_calls is False
    config_writer.set_tts_speak_calls(True, path=path)
    assert load_config(path).tts.speak_calls is True
