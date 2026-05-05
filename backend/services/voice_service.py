"""Speech-to-text and text-to-speech services."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile

import redis.asyncio as redis
from faster_whisper import WhisperModel
from pydub import AudioSegment

from config import settings

try:
    from elevenlabs.client import ElevenLabs
except ImportError:  # pragma: no cover
    ElevenLabs = None  # type: ignore[misc, assignment]


class VoiceService:
    """Local Whisper STT with optional ElevenLabs TTS and pyttsx3 fallback."""

    def __init__(self) -> None:
        self.whisper = WhisperModel(
            settings.WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
        )
        key = (settings.ELEVENLABS_API_KEY or "").strip()
        if key and ElevenLabs is not None:
            self.tts_client = ElevenLabs(api_key=key)
        else:
            self.tts_client = None
        self._redis_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=False,
        )

    async def _redis(self) -> redis.Redis:
        return redis.Redis(connection_pool=self._redis_pool)

    async def transcribe(self, audio_bytes: bytes) -> dict:
        """Transcribe uploaded audio with faster-whisper."""
        tmp_in = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
        tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        try:
            tmp_in.write(audio_bytes)
            tmp_in.flush()
            tmp_in.close()
            tmp_out.close()
            try:
                audio = await asyncio.to_thread(
                    AudioSegment.from_file,
                    tmp_in.name,
                )
                await asyncio.to_thread(audio.export, tmp_out.name, format="wav")
            except Exception:
                with open(tmp_in.name, "rb") as src, open(tmp_out.name, "wb") as dst:
                    dst.write(src.read())
            segments, info = await asyncio.to_thread(
                self.whisper.transcribe,
                tmp_out.name,
                beam_size=5,
                language=None,
            )
            texts = [s.text for s in segments]
            transcript = " ".join(texts).strip()
            return {
                "transcript": transcript,
                "language": info.language or "",
                "confidence": float(info.language_probability or 0.0),
                "duration_seconds": float(info.duration or 0.0),
            }
        finally:
            for path in (tmp_in.name, tmp_out.name):
                try:
                    os.unlink(path)
                except OSError:
                    pass

    async def synthesize(self, text: str) -> bytes:
        """Synthesize speech, using ElevenLabs when configured."""
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cache_key = f"tts:{digest}"
        client = await self._redis()
        try:
            cached = await client.get(cache_key)
        except redis.RedisError:
            cached = None
        if cached:
            return bytes(cached)

        clip = text[:2000]
        audio_bytes: bytes
        if self.tts_client is not None:
            try:

                def _gen() -> bytes:
                    stream = self.tts_client.generate(
                        text=clip,
                        voice=settings.ELEVENLABS_VOICE_ID,
                        model="eleven_multilingual_v2",
                    )
                    return b"".join(stream)

                audio_bytes = await asyncio.to_thread(_gen)
            except Exception:
                audio_bytes = await asyncio.to_thread(_pyttsx3_to_wav_bytes, clip)
        else:
            audio_bytes = await asyncio.to_thread(_pyttsx3_to_wav_bytes, clip)

        try:
            await client.set(cache_key, audio_bytes, ex=3600)
        except redis.RedisError:
            pass
        return audio_bytes


def _pyttsx3_to_wav_bytes(text: str) -> bytes:
    """Render speech to an in-memory WAV using pyttsx3."""
    import pyttsx3

    engine = pyttsx3.init()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_path = tmp.name
    try:
        engine.save_to_file(text, out_path)
        engine.runAndWait()
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


voice_service = VoiceService()
