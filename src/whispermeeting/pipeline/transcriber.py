"""Transcription pipeline built on top of faster-whisper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from faster_whisper import WhisperModel

from ..config import TranscriptionConfig


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


@dataclass
class Transcript:
    segments: List[TranscriptSegment]
    language: Optional[str]
    duration: Optional[float] = None


class FasterWhisperTranscriber:
    """Thin wrapper around faster-whisper with sane defaults."""

    def __init__(self, config: TranscriptionConfig) -> None:
        device = None if config.device == "auto" else config.device
        self.cfg = config
        try:
            self.model = WhisperModel(
                config.model_size,
                device=device or "auto",
                compute_type=config.compute_type,
            )
        except ValueError as exc:
            message = str(exc).lower()
            if "compute type" in message and config.compute_type != "int8":
                # Fall back to int8 for devices (e.g. CPU/MPS) that do not support int8_float16.
                self.model = WhisperModel(
                    config.model_size,
                    device=device or "auto",
                    compute_type="int8",
                )
                self.cfg.compute_type = "int8"
                print("[FasterWhisperTranscriber] Falling back to compute_type=int8 due to device limitations.", flush=True)
            else:
                raise

    def transcribe(self, audio_path: Path) -> Transcript:
        segments, info = self.model.transcribe(
            str(audio_path),
            beam_size=self.cfg.beam_size,
            language=self.cfg.language,
            task="translate" if self.cfg.translate_to_english else "transcribe",
            vad_filter=self.cfg.vad,
        )

        transcript_segments: List[TranscriptSegment] = []
        for seg in segments:
            transcript_segments.append(
                TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text.strip(),
                )
            )

        return Transcript(
            segments=transcript_segments,
            language=info.language if info else None,
            duration=info.duration if info else None,
        )

    def batch_transcribe(self, audio_files: Iterable[Path]) -> List[Transcript]:
        return [self.transcribe(audio) for audio in audio_files]
