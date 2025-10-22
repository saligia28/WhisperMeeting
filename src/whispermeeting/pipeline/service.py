"""High level orchestration for the meeting assistant workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .postprocessing import MeetingArtifacts, PostProcessor
from .transcriber import Transcript
from ..llm.summarizer import LocalLLMSummariser
from ..storage.repository import MeetingRepository


@dataclass
class PipelineOutput:
    meeting_id: str
    transcript: Transcript
    summary_markdown: str
    keywords: list[str]
    highlights: list[str]
    action_items: list[str]


class MeetingPipeline:
    """Runs transcription -> summarisation -> persistence for a meeting."""

    def __init__(
        self,
        transcriber,
        post_processor: PostProcessor,
        summariser: LocalLLMSummariser,
        repository: MeetingRepository,
    ) -> None:
        self.transcriber = transcriber
        self.post_processor = post_processor
        self.summariser = summariser
        self.repo = repository

    def run(
        self,
        meeting_id: str,
        audio_path: Path,
        vad_aggressiveness: Optional[int] = None,
        min_speech_ratio: Optional[float] = None,
    ) -> PipelineOutput:
        """Run the full pipeline with optional VAD parameter overrides.

        Args:
            meeting_id: Unique meeting identifier
            audio_path: Path to audio file
            vad_aggressiveness: Override VAD aggressiveness (0-3)
            min_speech_ratio: Override minimum speech ratio (0.3-0.8)
        """
        transcript = self.transcriber.transcribe(
            audio_path,
            vad_aggressiveness=vad_aggressiveness,
            min_speech_ratio=min_speech_ratio,
        )
        transcript = self.post_processor.enrich_transcript(transcript, audio_path)

        summary = self.summariser.predict(transcript)
        summary_markdown = self.post_processor.build_summary_markdown(transcript, summary.summary)
        keywords = self.post_processor.extract_keywords(transcript)

        artifacts = MeetingArtifacts(
            transcript=transcript,
            summary_markdown=summary_markdown,
            keywords=keywords,
        )
        self.post_processor.persist(meeting_id, artifacts)

        return PipelineOutput(
            meeting_id=meeting_id,
            transcript=transcript,
            summary_markdown=summary_markdown,
            keywords=keywords,
            highlights=summary.highlights,
            action_items=summary.action_items,
        )
