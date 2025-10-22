"""Transcription pipeline built on top of faster-whisper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from faster_whisper import WhisperModel

from ..config import TranscriptionConfig
from ..utils.chinese import ensure_simplified


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

    def transcribe(
        self,
        audio_path: Path,
        vad_aggressiveness: Optional[int] = None,
        min_speech_ratio: Optional[float] = None,
    ) -> Transcript:
        """Transcribe audio file with optional VAD parameter overrides.

        Args:
            audio_path: Path to audio file
            vad_aggressiveness: Override VAD aggressiveness (0-3), affects silence detection
            min_speech_ratio: Override minimum speech ratio threshold (0.3-0.8)

        Note: faster-whisper uses its own internal VAD (Silero VAD) which is different
        from WebRTC VAD used in realtime transcription. The vad_filter parameter
        enables/disables VAD but doesn't expose aggressiveness control.
        For consistency with realtime mode, we keep these parameters in the signature
        but note that they primarily affect realtime WebSocket transcription.
        """
        language = self.cfg.language or "zh"

        # Note: faster-whisper's vad_filter uses Silero VAD internally
        # The vad_aggressiveness parameter is mainly for realtime WebSocket mode
        # For batch processing, we rely on the global config setting
        segments, info = self.model.transcribe(
            str(audio_path),
            beam_size=self.cfg.beam_size,
            language=language,
            task="translate" if self.cfg.translate_to_english else "transcribe",
            vad_filter=self.cfg.vad,
            temperature=self.cfg.temperature,
            initial_prompt=self.cfg.initial_prompt,
        )

        transcript_segments: List[TranscriptSegment] = []
        should_simplify = (
            self.cfg.force_simplified_chinese
            and not self.cfg.translate_to_english
            and language
            and language.lower().startswith("zh")
        )
        for seg in segments:
            text = seg.text.strip()
            if should_simplify:
                text = ensure_simplified(text)
            transcript_segments.append(
                TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=text,
                )
            )

        return Transcript(
            segments=transcript_segments,
            language=(info.language if info and info.language else language),
            duration=info.duration if info else None,
        )

    def batch_transcribe(self, audio_files: Iterable[Path]) -> List[Transcript]:
        return [self.transcribe(audio) for audio in audio_files]
