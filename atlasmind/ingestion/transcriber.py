"""Audio transcription via OpenAI Whisper API.

Defines the Transcriber Protocol and the v0 implementation.
"""
from __future__ import annotations

import io
from typing import Protocol, runtime_checkable

from openai import AsyncOpenAI


@runtime_checkable
class Transcriber(Protocol):
    async def transcribe(self, audio_bytes: bytes, hint_filename: str) -> str: ...


class WhisperTranscriber:
    def __init__(self, api_key: str | None = None, model: str = "whisper-1") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def transcribe(self, audio_bytes: bytes, hint_filename: str) -> str:
        file_tuple = (hint_filename, io.BytesIO(audio_bytes))
        response = await self._client.audio.transcriptions.create(
            model=self._model,
            file=file_tuple,
        )
        return response.text
