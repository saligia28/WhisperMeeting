from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from whispermeeting.config import PostProcessingConfig, StorageConfig
from whispermeeting.pipeline.service import MeetingPipeline
from whispermeeting.pipeline.transcriber import Transcript, TranscriptSegment
from whispermeeting.storage.repository import MeetingRepository
from whispermeeting.pipeline.postprocessing import PostProcessor


class StubTranscriber:
    def transcribe(self, path: Path) -> Transcript:
        return Transcript(
            segments=[
                TranscriptSegment(start=0.0, end=1.0, text="Discuss roadmap", speaker="Alice"),
                TranscriptSegment(start=1.0, end=2.0, text="Finalize testing plan", speaker="Bob"),
            ],
            language="en",
            duration=120,
        )


class StubSummariser:
    def predict(self, transcript: Transcript):
        return SimpleNamespace(
            summary="Roadmap reviewed. Testing plan pending.",
            highlights=["Roadmap review"],
            action_items=["Bob to deliver testing plan"],
        )


def test_meeting_pipeline_persists_markdown(tmp_path):
    storage_cfg = StorageConfig(
        url=f"sqlite:///{tmp_path / 'test.db'}",
        audio_dir=tmp_path / "audio",
        transcripts_dir=tmp_path / "transcripts",
        summaries_dir=tmp_path / "summaries",
    )
    repo = MeetingRepository(storage_cfg)
    post_processor = PostProcessor(PostProcessingConfig(enable_speaker_diarization=False), repo)
    pipeline = MeetingPipeline(
        transcriber=StubTranscriber(),
        post_processor=post_processor,
        summariser=StubSummariser(),
        repository=repo,
    )

    meeting_id = uuid4().hex
    output = pipeline.run(meeting_id, tmp_path / "fake.wav")

    summary_path = storage_cfg.summaries_dir / f"{meeting_id}.md"
    assert summary_path.exists()
    assert "Roadmap reviewed" in summary_path.read_text(encoding="utf-8")
    assert output.keywords  # keywords extracted
