"""Speaker diarization abstractions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

try:
    from pyannote.audio import Pipeline  # type: ignore
except ImportError:  # pragma: no cover
    Pipeline = None  # type: ignore


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


class DiarizationService:
    """Wraps pyannote or other diarization backends."""

    def __init__(self, model_name: str = "pyannote/speaker-diarization") -> None:
        self.model_name = model_name
        self.pipeline = None
        if Pipeline:
            self.pipeline = Pipeline.from_pretrained(model_name)  # type: ignore[call-arg]

    def run(self, audio_path: Path) -> List[SpeakerTurn]:
        if not self.pipeline:
            raise RuntimeError("pyannote.audio is not installed or pipeline failed to load.")

        diarization = self.pipeline(audio_path)
        turns: List[SpeakerTurn] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append(SpeakerTurn(start=turn.start, end=turn.end, speaker=speaker))
        return turns

    @staticmethod
    def apply(transcript_segments, turns: Iterable[SpeakerTurn]):
        turns = list(turns)
        for segment in transcript_segments:
            for turn in turns:
                if turn.start <= segment.start <= turn.end:
                    segment.speaker = turn.speaker
                    break
