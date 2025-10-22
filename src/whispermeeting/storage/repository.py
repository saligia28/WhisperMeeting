"""Persistence layer built on top of SQLModel."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from sqlmodel import Field, Session, SQLModel, create_engine, delete, select

from ..config import StorageConfig
from ..pipeline.transcriber import Transcript, TranscriptSegment


class Meeting(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str | None = None
    language: str | None = None
    duration: float | None = None


class TranscriptRow(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: str = Field(foreign_key="meeting.id")
    start: float
    end: float
    text: str
    speaker: str | None = None


class Summary(SQLModel, table=True):
    meeting_id: str = Field(primary_key=True)
    markdown: str
    keywords: str


class UserSettings(SQLModel, table=True):
    """User preferences for VAD parameters and other settings."""
    user_id: str = Field(primary_key=True)
    vad_aggressiveness: int = Field(default=1, ge=0, le=3)  # 降低到1，更宽松的VAD检测
    min_speech_ratio: float = Field(default=0.3, ge=0.3, le=0.8)  # 降低到30%，更容易触发转录


class MeetingRepository:
    """Simple repository storing data on disk."""

    def __init__(self, config: StorageConfig) -> None:
        self.cfg = config
        self.cfg.audio_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.summaries_dir.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(self.cfg.url)
        SQLModel.metadata.create_all(self.engine)

    def save_transcript(self, meeting_id: str, transcript: Transcript) -> None:
        with Session(self.engine) as session:
            meeting = session.get(Meeting, meeting_id)
            if not meeting:
                meeting = Meeting(
                    id=meeting_id,
                    title=f"会议 {meeting_id}",
                    language=transcript.language,
                    duration=transcript.duration,
                )
                session.add(meeting)
            else:
                meeting.language = transcript.language or meeting.language
                meeting.duration = transcript.duration or meeting.duration

            session.exec(delete(TranscriptRow).where(TranscriptRow.meeting_id == meeting_id))

            for seg in transcript.segments:
                row = TranscriptRow(
                    meeting_id=meeting_id,
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    speaker=seg.speaker,
                )
                session.add(row)

            session.commit()

    def save_summary(self, meeting_id: str, markdown: str, keywords: Iterable[str]) -> None:
        keywords_str = ",".join(keywords)
        with Session(self.engine) as session:
            summary = session.get(Summary, meeting_id)
            if summary:
                summary.markdown = markdown
                summary.keywords = keywords_str
            else:
                summary = Summary(
                    meeting_id=meeting_id,
                    markdown=markdown,
                    keywords=keywords_str,
                )
                session.add(summary)
            session.commit()

            summary_path = Path(self.cfg.summaries_dir) / f"{meeting_id}.md"
            summary_path.write_text(markdown, encoding="utf-8")

    def get_summary(self, meeting_id: str) -> Optional[str]:
        with Session(self.engine) as session:
            summary = session.get(Summary, meeting_id)
            return summary.markdown if summary else None

    def list_meetings(self) -> list[Meeting]:
        with Session(self.engine) as session:
            result = session.exec(select(Meeting)).all()
            return result

    def get_transcript_segments(self, meeting_id: str) -> list[TranscriptSegment]:
        with Session(self.engine) as session:
            rows = (
                session.exec(
                    select(TranscriptRow)
                    .where(TranscriptRow.meeting_id == meeting_id)
                    .order_by(TranscriptRow.start)
                )
                .all()
            )
            return [
                TranscriptSegment(
                    start=row.start,
                    end=row.end,
                    text=row.text,
                    speaker=row.speaker,
                )
                for row in rows
            ]

    def create_meeting(self, meeting_id: str, title: str | None = None, language: str | None = None) -> Meeting:
        with Session(self.engine) as session:
            meeting = session.get(Meeting, meeting_id)
            if meeting:
                meeting.title = title or meeting.title
                if language:
                    meeting.language = language
            else:
                meeting = Meeting(id=meeting_id, title=title, language=language)
                session.add(meeting)
            session.commit()
            session.refresh(meeting)
            return meeting

    def delete_meeting(self, meeting_id: str) -> bool:
        """Remove a meeting and all related data. Returns False if the meeting does not exist."""
        summary_path = Path(self.cfg.summaries_dir) / f"{meeting_id}.md"

        with Session(self.engine) as session:
            meeting = session.get(Meeting, meeting_id)
            if not meeting:
                return False

            session.exec(delete(TranscriptRow).where(TranscriptRow.meeting_id == meeting_id))
            session.exec(delete(Summary).where(Summary.meeting_id == meeting_id))
            session.delete(meeting)
            session.commit()

        summary_path.unlink(missing_ok=True)
        return True

    def get_user_settings(self, user_id: str) -> UserSettings:
        """Get user settings, creating default if not exists."""
        with Session(self.engine) as session:
            settings = session.get(UserSettings, user_id)
            if not settings:
                settings = UserSettings(user_id=user_id)
                session.add(settings)
                session.commit()
                session.refresh(settings)
            return settings

    def update_user_settings(
        self,
        user_id: str,
        vad_aggressiveness: Optional[int] = None,
        min_speech_ratio: Optional[float] = None,
    ) -> UserSettings:
        """Update user settings and return the updated object."""
        with Session(self.engine) as session:
            settings = session.get(UserSettings, user_id)
            if not settings:
                settings = UserSettings(user_id=user_id)
                session.add(settings)

            if vad_aggressiveness is not None:
                settings.vad_aggressiveness = max(0, min(3, vad_aggressiveness))
            if min_speech_ratio is not None:
                settings.min_speech_ratio = max(0.3, min(0.8, min_speech_ratio))

            session.commit()
            session.refresh(settings)
            return settings
