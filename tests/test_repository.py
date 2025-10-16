from pathlib import Path
from uuid import uuid4

from whispermeeting.config import StorageConfig
from whispermeeting.pipeline.transcriber import Transcript, TranscriptSegment
from whispermeeting.storage.repository import MeetingRepository


def make_transcript():
    return Transcript(
        segments=[
            TranscriptSegment(start=0.0, end=1.0, text="Hello world", speaker="Alice"),
            TranscriptSegment(start=1.0, end=2.0, text="Testing repo", speaker="Bob"),
        ],
        language="en",
        duration=120,
    )


def test_repository_persists_and_lists(tmp_path):
    storage_cfg = StorageConfig(
        url=f"sqlite:///{tmp_path / 'repo.db'}",
        audio_dir=tmp_path / "audio",
        transcripts_dir=tmp_path / "transcripts",
        summaries_dir=tmp_path / "summaries",
    )
    repo = MeetingRepository(storage_cfg)

    meeting_id = uuid4().hex
    repo.save_transcript(meeting_id, make_transcript())
    repo.save_summary(meeting_id, "# Summary", ["keyword"])

    meetings = repo.list_meetings()
    assert meetings
    assert meetings[0].id == meeting_id

    summary = repo.get_summary(meeting_id)
    assert summary == "# Summary"
