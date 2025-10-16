"""Post processing helpers for transcripts and summaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..config import PostProcessingConfig
from ..pipeline.diarization import DiarizationService
from ..pipeline.transcriber import Transcript, TranscriptSegment
from ..storage.repository import MeetingRepository


@dataclass
class MeetingArtifacts:
    transcript: Transcript
    summary_markdown: str
    keywords: list[str]


class PostProcessor:
    """Coordinates diarization, keyword extraction and persistence."""

    def __init__(self, config: PostProcessingConfig, repository: MeetingRepository) -> None:
        self.cfg = config
        self.repo = repository
        self._diarizer = (
            DiarizationService(config.diarization_model) if config.enable_speaker_diarization else None
        )

    def enrich_transcript(self, transcript: Transcript, audio_path: Path) -> Transcript:
        # Diarization would be applied here; we keep a placeholder to avoid heavy deps in tests.
        if self.cfg.enable_speaker_diarization:
            if self._diarizer:
                try:
                    turns = self._diarizer.run(audio_path)
                    self._diarizer.apply(transcript.segments, turns)
                except Exception as exc:  # pragma: no cover - best effort
                    print(f"[PostProcessor] Diarization failed: {exc}")
                    for segment in transcript.segments:
                        segment.speaker = segment.speaker or "Speaker"
            else:
                for segment in transcript.segments:
                    segment.speaker = segment.speaker or "Speaker"
        return transcript

    def build_summary_markdown(self, transcript: Transcript, summary_text: str) -> str:
        lines = [
            "# Meeting Summary",
            "",
            summary_text,
            "",
            "## Transcript",
        ]
        for seg in transcript.segments:
            lines.append(f"- **{seg.speaker or 'Speaker'} [{seg.start:.02f}-{seg.end:.02f}]**: {seg.text}")
        return "\n".join(lines)

    def extract_keywords(self, transcript: Transcript, limit: int = 10) -> list[str]:
        vocab = {}
        for seg in transcript.segments:
            for token in seg.text.lower().split():
                token = token.strip(".,:;?!")
                if len(token) < 4:
                    continue
                vocab[token] = vocab.get(token, 0) + 1
        keywords = sorted(vocab.items(), key=lambda item: item[1], reverse=True)
        return [kw for kw, _ in keywords[:limit]]

    def persist(self, meeting_id: str, artifacts: MeetingArtifacts) -> None:
        self.repo.save_transcript(meeting_id, artifacts.transcript)
        self.repo.save_summary(meeting_id, artifacts.summary_markdown, artifacts.keywords)
