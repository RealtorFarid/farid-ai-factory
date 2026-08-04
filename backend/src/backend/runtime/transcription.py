"""Speech to text.

The operator talks after a showing; everything downstream works on the
transcript. Behind a protocol so the provider is replaceable — transcription is
a commodity and should never be load-bearing on one vendor.

Cost: audio is billed per minute, not per token, and a post-showing note is
30-90 seconds. That is the cheapest input in the product for the amount of
memory it produces, which is exactly why voice is the wedge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.runtime.config import Settings
from backend.runtime.logger import get_logger

__all__ = [
    "StubTranscriber",
    "Transcriber",
    "Transcript",
    "TranscriptionError",
    "build_transcriber",
]

log = get_logger(__name__)

#: Formats a browser MediaRecorder realistically produces, plus phone uploads.
SUPPORTED_AUDIO = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mpga": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
}


class TranscriptionError(RuntimeError):
    """Transcription failed. The recording is kept so it can be retried."""


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    #: ISO-639-1 where the provider reports it. Drives which language the
    #: extraction replies in, so a Persian note stays Persian.
    language: str | None
    duration_seconds: float | None


class Transcriber(Protocol):
    async def transcribe(self, *, audio: bytes, filename: str, content_type: str) -> Transcript: ...


class OpenAITranscriber:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe(self, *, audio: bytes, filename: str, content_type: str) -> Transcript:
        try:
            result = await self._client.audio.transcriptions.create(
                model=self._model,
                file=(filename, audio, content_type),
                # `verbose_json` is the only format that reports the detected
                # language, which the multilingual path depends on.
                response_format="verbose_json",
            )
        except Exception as exc:
            log.warning("transcription.failed", error=str(exc), bytes=len(audio))
            raise TranscriptionError(str(exc)) from exc

        text = getattr(result, "text", "") or ""
        language = getattr(result, "language", None)
        duration = getattr(result, "duration", None)

        log.info(
            "transcription.completed",
            chars=len(text),
            language=language,
            seconds=duration,
            bytes=len(audio),
        )
        return Transcript(
            text=text.strip(),
            language=_iso_639_1(language),
            duration_seconds=float(duration) if duration is not None else None,
        )


class StubTranscriber:
    """Offline transcriber, so voice capture is demonstrable with no key."""

    #: Persian, to exercise the multilingual path rather than the easy one.
    SAMPLE = "امروز با پریا و همسرش رضا ملاقات کردم. آنها می‌خواهند قبل از سپتامبر نقل مکان کنند."

    async def transcribe(self, *, audio: bytes, filename: str, content_type: str) -> Transcript:
        seconds = max(1.0, len(audio) / 16_000)
        return Transcript(text=self.SAMPLE, language="fa", duration_seconds=seconds)


#: Whisper reports some languages by English name rather than code.
_LANGUAGE_NAMES = {
    "english": "en",
    "persian": "fa",
    "farsi": "fa",
    "spanish": "es",
    "french": "fr",
    "arabic": "ar",
    "chinese": "zh",
    "hindi": "hi",
}


def _iso_639_1(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().lower()
    if len(text) == 2:
        return text
    return _LANGUAGE_NAMES.get(text, text[:2])


def build_transcriber(settings: Settings) -> Transcriber:
    if settings.default_model == "stub" or not settings.llm_configured:
        return StubTranscriber()
    assert settings.openai_api_key is not None
    return OpenAITranscriber(
        settings.openai_api_key.get_secret_value(), settings.transcription_model
    )
