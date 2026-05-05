"""Voice transcription and speech synthesis."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dependencies import get_current_user
from models.user import User
from services.voice_service import voice_service

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


class SynthesizeBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
) -> dict:
    """Transcribe an uploaded audio clip."""
    _ = current
    try:
        audio_bytes = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read upload: {exc!s}",
        ) from exc
    if not audio_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    try:
        out = await voice_service.transcribe(audio_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {exc!s}",
        ) from exc

    if isinstance(out, dict) and out.get("error"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=out["error"],
        )
    return out


def byte_iterator(data: bytes):
    yield data


@router.post("/synthesize")
async def synthesize_speech(
    body: SynthesizeBody,
    current: User = Depends(get_current_user),
) -> StreamingResponse:
    """Synthesize speech audio from text."""
    _ = current
    try:
        audio = await voice_service.synthesize(body.text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Synthesis failed: {exc!s}",
        ) from exc

    media_type = "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg"
    return StreamingResponse(
        byte_iterator(audio),
        media_type=media_type,
        headers={"Cache-Control": "no-cache"},
    )
